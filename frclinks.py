# Copyright 2008 Patrick Fairbank. All Rights Reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR "AS IS" AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO
# EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
# IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""
Provides URL shortcuts for various areas of the FIRST website, such as team info
pages, event team lists, documents and updates. Intended to compensate for the
FIRST website's use of non-memorable URLs and lack of ease of navigation.
"""

import json
import os
import re
import urllib

from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from team import FlushTeams
from team import LookupTeam
from team import ScrapeTeam
from team import ScrapeTeams

# Extracts the team number from the end of the URL.
numberRe = re.compile(r'\d+')

# Extracts the area code from the end of the URL.
areaRe = re.compile(r'[A-Za-z\-]+')

# Extracts the event code from the end of the URL.
eventRe = re.compile(r'[A-Za-z]+\d?')

# Extracts the year from the end of the URL.
yearRe = re.compile(r'\d{4}')

# Get the team and the year from the URL
blueAllianceRe = re.compile(r'(\d+)/?(\d{4})?')

# Extracts the team webpage from the FIRST team info page.
websiteRe = re.compile(r'Team Website:.*href="(http://[A-Za-z0-9\.\-_/#]+)')

# Extracts team scrape parameters.
scrapeTeamsRe = re.compile(r'(\d{4})/(\d+)')

# Extracts the requested manual section.
sectionRe = re.compile(r'/([iagrt])')

# Extracts a session code.
sessionRe = re.compile(r'session=myarea:([A-Za-z0-9]+)')

# Year to default to for event information if none is provided.
defaultYear = '2015'

# Base url for many FRC pages.
frcUrl = 'http://www.usfirst.org/roboticsprograms/frc/'

# Mapping of years to year-specific pages.
regionalYears = {'default':frcUrl + 'regionalevents.aspx?id=430',
                 '2014':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2014&archive=true',
                 '2013':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2013&archive=true',
                 '2012':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2012&archive=true',
                 '2011':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2011&archive=true',
                 '2010':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2010&archive=true',
                 '2009':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2009&archive=true',
                 '2008':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2008&archive=true',
                 '2007':'https://my.usfirst.org/myarea/index.lasso?' +
                     'event_type=FRC&year=2007&archive=true',
                 '2006':frcUrl + 'content.aspx?id=4188',
                 '2005':frcUrl + 'content.aspx?id=4388',}
championshipYears = {'default':frcUrl + 'content.aspx?id=432',
                     '2009':frcUrl + 'content.aspx?id=14716',  # No special page exists from 2010 onwards.
                     '2008':frcUrl + 'content.aspx?id=11286',
                     '2007':frcUrl + 'content.aspx?id=6778',
                     '2006':frcUrl + 'content.aspx?id=4188',
                     '2005':frcUrl + 'content.aspx?id=4388',
                     '2004':frcUrl + 'content.aspx?id=9302',
                     '2003':frcUrl + 'content.aspx?id=9304',}
documentsYears = {'default':frcUrl + 'competition-manual-and-related-documents',
                  '2013':frcUrl + '2013-competition-manual-and-related-documents',
                  '2012':frcUrl + '2012-competition-manual-and-related-documents',
                  '2011':frcUrl + '2011-competition-manual-and-related-documents',
                  '2010':frcUrl + 'content.aspx?id=18068',
                  '2009':frcUrl + 'content.aspx?id=15523',
                  '2008':frcUrl + 'content.aspx?id=9152',
                  '2007':frcUrl + 'content.aspx?id=7430',
                  '2006':frcUrl + 'content.aspx?id=3630',}

# Pre-compute the event list for the instructions page.
eventList = json.load(open("events.json"))
events = []
for i in xrange(0, (len(eventList) + 2) / 3):
  row = [eventList[i]['code'], eventList[i]['name']]
  j = i + (len(eventList) + 2) / 3
  row.append(eventList[j]['code'])
  row.append(eventList[j]['name'])
  k = j + (len(eventList) + 2) / 3
  if k < len(eventList):
    row.append(eventList[k]['code'])
    row.append(eventList[k]['name'])
  events.append(row)

# Pre-compute the event code translation tables.
newToOldEventCodes = {}
oldToNewEventCodes = {}
for event in eventList:
  newToOldEventCodes[event['code']] = event['old_code']
  oldToNewEventCodes[event['old_code']] = event['code']

def GetYear(handler):
  endNumber = yearRe.findall(handler.request.path)
  if len(endNumber) > 0:
    return endNumber[-1]
  else:
    return defaultYear

def GetEvent(handler):
  event = eventRe.findall(handler.request.path)[-1]
  year = int(GetYear(handler))
  if year < 2013 and newToOldEventCodes.has_key(event):
    event = newToOldEventCodes[event]
  elif year >= 2013 and oldToNewEventCodes.has_key(event):
    event = oldToNewEventCodes[event]

  if event == 'arc':
    event = 'archimedes'
  elif event == 'cur':
    event = 'curie'
  elif event == 'gal':
    event = 'galileo'
  elif event == 'new':
    event = 'newton'
  elif event == 'ein':
    event = 'einstein'
  return event

def GetTeamPageUrl(handler):
    team = numberRe.findall(handler.request.path)[-1]

    # Try checking the datastore for the team's most recent tpid.
    tpid = LookupTeam(team)

    if not tpid:
      # Otherwise, try scraping the FIRST website for the current season's tpid.
      tpid = ScrapeTeam(team, defaultYear)

    if tpid:
      return ('http://www.usfirst.org/whats-going-on/team/' + tpid +
                  '/?ProgramCode=FRC')

    return None

def Redir(handler, url):
  if 'my.usfirst.org/myarea' in url:
    # FIRST is now checking the 'Referer' header for the string 'usfirst.org'.
    handler.redirect('/usfirst.org?' + urllib.urlencode({ 'url' : url }))
  else:
    handler.response.out.write(
        template.render('templates/redirect.html', { 'url' : url, }))

class TeamPage(webapp.RequestHandler):
  """
  Redirects the user to the given team's FIRST information page.
  """
  def get(self):
    teamPageUrl = GetTeamPageUrl(self)
    if teamPageUrl:
      Redir(self, teamPageUrl)
    else:
      team = numberRe.findall(self.request.path)[-1]
      template_values = {
        'team': team,
      }
      path = 'templates/no_team.html'
      self.response.out.write(template.render(path, template_values))

class AreaTeamListPage(webapp.RequestHandler):
  """
  Redirects the user to the team list for the given area.
  """
  def get(self):
    area = areaRe.findall(self.request.path)[-1]
    Redir(self, 'https://my.usfirst.org/myarea/index.lasso?page=searchresults' +
                  '&programs=FRC&reports=teams&sort_teams=number&results_size' +
                  '=250&omit_searchform=1&season_FRC=' + GetYear(self) +
                  '&area=' + area)

class TeamWebsitePage(webapp.RequestHandler):
  """
  Redirects the user to the team website listed on the given team's FIRST
  information page.
  """
  def get(self):
    teamPageUrl = GetTeamPageUrl(self)
    team = numberRe.findall(self.request.path)[-1]
    if not teamPageUrl:
      template_values = {
        'team': team,
      }
      path = 'templates/no_team.html'
      self.response.out.write(template.render(path, template_values))
    else:
      teamPage = urlfetch.fetch(teamPageUrl, deadline=10)
      website = websiteRe.findall(teamPage.content)
      if len(website) == 0:
        template_values = {
          'team': team,
        }
        path = 'templates/no_website.html'
        self.response.out.write(template.render(path, template_values))
      else:
        Redir(self, website[0])

class TeamTheBlueAlliancePage(webapp.RequestHandler):
  """
  Redirects the user to the given team's The Blue Alliance page.
  """
  def get(self):
    team, year = blueAllianceRe.findall(self.request.path)[-1]
    if len(year) == 0:
      year = defaultYear
    Redir(self, 'http://www.thebluealliance.com/team/%s/%s' % (team, year))

class TeamChiefDelphiMediaPage(webapp.RequestHandler):
  """
  Redirects the user to the given team's Chief Delphi Media page.
  """
  def get(self):
    team = numberRe.findall(self.request.path)[-1]
    Redir(self, 'http://www.chiefdelphi.com/media/photos/tags/frc' + team)

class AllTeamsPage(webapp.RequestHandler):
  """
  Redirects the user to the list of all registered FRC teams.
  """
  def get(self):
    Redir(self, 'https://my.usfirst.org/myarea/index.lasso?page=searchresults' +
                  '&programs=FRC&reports=teams&sort_teams=number&results_size' +
                  '=250&omit_searchform=1&season_FRC=' + defaultYear)

class EventTeamListPage(webapp.RequestHandler):
  """
  Redirects the user to the team list for the given event.
  """
  def get(self):
    event = GetEvent(self)
    year = GetYear(self)

    if event == 'archimedes':
      event = 'cmp&division=archimedes'
    elif event == 'curie':
      event = 'cmp&division=curie'
    elif event == 'galileo':
      event = 'cmp&division=galileo'
    elif event == 'newton':
      event = 'cmp&division=newton'
    Redir(self, 'https://my.usfirst.org/myarea/index.lasso?' +
                  'page=teamlist&event_type=FRC&sort_teams=number' +
                  '&year=' + year +
                  '&event=' + event)

class EventSchedulePage(webapp.RequestHandler):
  """
  Redirects the user to the qualification match schedule for the given event.
  """
  def get(self):
    Redir(self, 'http://www2.usfirst.org/' + GetYear(self) + 'comp/Events/' +
                  GetEvent(self) + '/ScheduleQual.html')

class EventMatchResultsPage(webapp.RequestHandler):
  """
  Redirects the user to the qualification match results for the given event.
  """
  def get(self):
    year = GetYear(self)
    event = GetEvent(self)

    # In 2005, 2006 and 2008 the code "einstein" was used instead of "cmp".
    if event == 'cmp':
      if year == '2005' or year == '2006' or year == '2008':
        event = 'einstein'

    if (year == '2007' or year == '2006' or year == '2004'):
      Redir(self, 'http://www2.usfirst.org/' + year + 'comp/Events/' + event
                    + '/matches.html')
    elif year == '2003':
      Redir(self, 'http://www2.usfirst.org/' + year + 'comp/Events/' + event
                    + '/matchsum.html')
    else:
      Redir(self, 'http://www2.usfirst.org/' + year + 'comp/Events/' + event
                    + '/matchresults.html')

class EventRankingsPage(webapp.RequestHandler):
  """
  Redirects the user to the rankings for the given event.
  """
  def get(self):
    Redir(self, 'http://www2.usfirst.org/' + GetYear(self) + 'comp/Events/' +
                  GetEvent(self) + '/rankings.html')

class EventAwardsPage(webapp.RequestHandler):
  """
  Redirects the user to the awards for the given event.
  """
  def get(self):
    year = GetYear(self)
    event = GetEvent(self)

    # In 2005, 2006 and 2008 the code "einstein" was used instead of "cmp".
    if event == 'cmp':
      if year == '2005' or year == '2006' or year == '2008':
        event = 'einstein'

    Redir(self, 'http://www2.usfirst.org/' + year + 'comp/Events/' + event
                  + '/awards.html')

class EventAgendaPage(webapp.RequestHandler):
  """
  Redirects the user to the public agenda for the given event.
  """
  def get(self):
    year = GetYear(self)
    event = GetEvent(self)

    Redir(self, 'http://www.usfirst.org/uploadedFiles/Robotics_Programs/FRC/'
                  + 'Events/%s/%s_%s_Agenda.pdf' % (year, year, event.upper()))

class EventTheBlueAlliancePage(webapp.RequestHandler):
  """
  Redirects the user to the The Blue Alliance page for the given event.
  """
  def get(self):
    event = GetEvent(self)
    if event == 'archimedes':
      event = 'arc'
    elif event == 'curie':
      event = 'cur'
    elif event == 'galileo':
      event = 'gal'
    elif event == 'newton':
      event = 'new'
    elif event == 'einstein':
      event = 'ein'
    Redir(self, 'http://www.thebluealliance.com/event/' + GetYear(self) + event)

class RegionalsPage(webapp.RequestHandler):
  """
  Redirects the user to the Regional Events page.
  """
  def get(self):
    year = GetYear(self)
    if regionalYears.has_key(year):
      Redir(self, regionalYears.get(year))
    else:
      Redir(self, regionalYears.get('default'))

class ChampionshipPage(webapp.RequestHandler):
  """
  Redirects the user to the Championship Event page.
  """
  def get(self):
    year = GetYear(self)
    if championshipYears.has_key(year):
      Redir(self, championshipYears.get(year))
    else:
      Redir(self, championshipYears.get('default'))

class ControlSystemPage(webapp.RequestHandler):
  """
  Redirects the user to the 2012 Control System page.
  """
  def get(self):
    Redir(self, frcUrl + '2012-kit-of-parts-control-system')

class DocumentsPage(webapp.RequestHandler):
  """
  Redirects the user to the Competition Manual page.
  """
  def get(self):
    year = GetYear(self)
    if documentsYears.has_key(year):
      Redir(self, documentsYears.get(year))
    else:
      Redir(self, documentsYears.get('default'))

class KitOfPartsPage(webapp.RequestHandler):
  """
  Redirects the user to the Kit of Parts page.
  """
  def get(self):
    Redir(self, frcUrl + 'kit-of-parts')

class UpdatesPage(webapp.RequestHandler):
  """
  Redirects the user to the Team Updates page.
  """
  def get(self):
    Redir(self, 'http://frc-manual.usfirst.org/Updates/0')

class BlogPage(webapp.RequestHandler):
  """
  Redirects the user to Bill's Blog.
  """
  def get(self):
    Redir(self, frcUrl + 'blog')

class ForumsPage(webapp.RequestHandler):
  """
  Redirects the user to the FIRST forums.
  """
  def get(self):
    Redir(self, 'http://forums.usfirst.org')

class QAPage(webapp.RequestHandler):
  """
  Redirects the user to the Q&A forum.
  """
  def get(self):
    Redir(self, 'https://frc-qa.usfirst.org/Questions.php')

class NewsPage(webapp.RequestHandler):
  """
  Redirects the user to the FRC news page.
  """
  def get(self):
    Redir(self, frcUrl + 'emailblastarchive.aspx')

class YouTubePage(webapp.RequestHandler):
  """
  Redirects the user to the FRC YouTube channel.
  """
  def get(self):
    Redir(self, 'http://www.youtube.com/user/FRCTeamsGlobal')

class TIMSPage(webapp.RequestHandler):
  """
  Redirects the user to the FRC Team Information Management System (TIMS).
  """
  def get(self):
    Redir(self, 'https://my.usfirst.org/frc/tims/site.lasso')

class STIMSPage(webapp.RequestHandler):
  """
  Redirects the user to the Student Team Information Member System (TIMS).
  """
  def get(self):
    Redir(self, 'https://my.usfirst.org/stims/site.lasso')

class VIMSPage(webapp.RequestHandler):
  """
  Redirects the user to the Volunteer Information & Matching System (VIMS).
  """
  def get(self):
    Redir(self, 'https://my.usfirst.org/FIRSTPortal/Login/VIMS_Login.aspx')

class KickoffPage(webapp.RequestHandler):
  """
  Redirects the user to the FRC Kickoff Page from FIRST
  """
  def get(self):
    Redir(self, frcUrl + 'kickoff')

class CalendarPage(webapp.RequestHandler):
  """
  Redirects the user to the FRC Calendar of Events.
  """
  def get(self):
    Redir(self, frcUrl + 'calendar')

class CookiePage(webapp.RequestHandler):
  """
  ???
  """
  def get(self):
    Redir(self, 'http://www.chiefdelphi.com/media/photos/33801')

class FlushTeamsPage(webapp.RequestHandler):
  """
  Deletes 500 teams at a time from the datastore (Google limit).
  Unlisted on the instructions page; intended for admin use.
  """
  def get(self):
    FlushTeams()
    path = 'templates/instructions.html'
    self.response.out.write(template.render(path, {}))

class ScrapeTeamsPage(webapp.RequestHandler):
  """
  Retrieves and caches teams from the given year in the datastore.
  Unlisted on the instructions page; intended for admin use.
  """
  def get(self):
    scrapeTeamsMatch = scrapeTeamsRe.findall(self.request.path)
    ScrapeTeams(scrapeTeamsMatch[-1][0], scrapeTeamsMatch[-1][1])
    path = 'templates/instructions.html'
    self.response.out.write(template.render(path, {}))

class InstructionPage(webapp.RequestHandler):
  """
  Displays the complete list of commands for this application.
  """
  def get(self):
    path = 'templates/instructions.html'
    self.response.out.write(template.render(path, { 'events' : events }))

class RobotsTxtPage(webapp.RequestHandler):
  """
  Displays the robots.txt file.
  """
  def get(self):
    self.response.headers.add_header('content-type', 'text/plain')
    self.response.out.write('User-agent: *\nDisallow:')

class GetFRCSpyDump(webapp.RequestHandler):
  """
  Gets the latest CSV dump from Chief Delphi FRC-Spy (Twitter @FRCFMS data)
  """
  def get(self):
    Redir(self, 'http://www.chiefdelphi.com/forums/frcspy.php?xml=csv')

class ReferrerRedirectPage(webapp.RequestHandler):
  """
  Redirects to fool FIRST's referrer-based checking.
  """
  def get(self):
    self.response.out.write(template.render(
        'templates/redirect.html', { 'url' : self.request.get('url'), }))

# The mapping of URLs to handlers. For some reason, regular expressions that
# use parentheses (e.g. '(championship|cmp|c)') cause an error, so some
# duplication exists.
application = webapp.WSGIApplication([
    (r'/teams?/\d+/?', TeamPage),
    (r'/t/\d+/?', TeamPage),
    (r'/teams?/[A-Za-z\-]+/\d{4}/?', AreaTeamListPage),
    (r'/teams?/[A-Za-z\-]+/?', AreaTeamListPage),
    (r'/t/[A-Za-z\-]+/\d{4}/?', AreaTeamListPage),
    (r'/t/[A-Za-z\-]+/?', AreaTeamListPage),
    (r'/t/\d+/?', TeamPage),
    (r'/website/\d+/?', TeamWebsitePage),
    (r'/w/\d+/?', TeamWebsitePage),
    (r'/tba/\d+/\d{4}/?', TeamTheBlueAlliancePage),
    (r'/tba/\d+/?', TeamTheBlueAlliancePage),
    (r'/cdm/\d+/?', TeamChiefDelphiMediaPage),
    (r'/teams?/?', AllTeamsPage),
    (r'/t/?', AllTeamsPage),
    (r'/events?/schedule/[A-Za-z]+\d?/\d{4}/?', EventSchedulePage),
    (r'/events?/schedule/[A-Za-z]+\d?/?', EventSchedulePage),
    (r'/e/s/[A-Za-z]+\d?/\d{4}/?', EventSchedulePage),
    (r'/e/s/[A-Za-z]+\d?/?', EventSchedulePage),
    (r'/events?/matchresults/[A-Za-z]+\d?/\d{4}/?', EventMatchResultsPage),
    (r'/events?/matchresults/[A-Za-z]+\d?/?', EventMatchResultsPage),
    (r'/e/m/[A-Za-z]+\d?/\d{4}/?', EventMatchResultsPage),
    (r'/e/m/[A-Za-z]+\d?/?', EventMatchResultsPage),
    (r'/events?/rankings/[A-Za-z]+\d?/\d{4}/?', EventRankingsPage),
    (r'/events?/rankings/[A-Za-z]+\d?/?', EventRankingsPage),
    (r'/e/r/[A-Za-z]+\d?/\d{4}/?', EventRankingsPage),
    (r'/e/r/[A-Za-z]+\d?/?', EventRankingsPage),
    (r'/events?/awards/[A-Za-z]+\d?/\d{4}/?', EventAwardsPage),
    (r'/events?/awards/[A-Za-z]+\d?/?', EventAwardsPage),
    (r'/e/a/[A-Za-z]+\d?/\d{4}/?', EventAwardsPage),
    (r'/e/a/[A-Za-z]+\d?/?', EventAwardsPage),
    (r'/events?/agenda/[A-Za-z]+\d?/\d{4}/?', EventAgendaPage),
    (r'/events?/agenda/[A-Za-z]+\d?/?', EventAgendaPage),
    (r'/e/g/[A-Za-z]+\d?/\d{4}/?', EventAgendaPage),
    (r'/e/g/[A-Za-z]+\d?/?', EventAgendaPage),
    (r'/events?/tba/[A-Za-z]+\d?/\d{4}/?', EventTheBlueAlliancePage),
    (r'/events?/tba/[A-Za-z]+\d?/?', EventTheBlueAlliancePage),
    (r'/e/tba/[A-Za-z]+\d?/\d{4}/?', EventTheBlueAlliancePage),
    (r'/e/tba/[A-Za-z]+\d?/?', EventTheBlueAlliancePage),
    (r'/events?/[A-Za-z]+\d?/\d{4}/?', EventTeamListPage),
    (r'/events?/[A-Za-z]+\d?/?', EventTeamListPage),
    (r'/e/[A-Za-z]+\d?/\d{4}/?', EventTeamListPage),
    (r'/e/[A-Za-z]+\d?/?', EventTeamListPage),
    (r'/regionals/\d{4}/?', RegionalsPage),
    (r'/regionals/?', RegionalsPage),
    (r'/r/\d{4}/?', RegionalsPage),
    (r'/r/?', RegionalsPage),
    (r'/championship/\d{4}/?', ChampionshipPage),
    (r'/championship/?', ChampionshipPage),
    (r'/cmp/\d{4}/?', ChampionshipPage),
    (r'/cmp/?', ChampionshipPage),
    (r'/c/\d{4}/?', ChampionshipPage),
    (r'/c/?', ChampionshipPage),
    (r'/controlsystem/?', ControlSystemPage),
    (r'/cs/?', ControlSystemPage),
    (r'/documents/?', DocumentsPage),
    (r'/docs/\d{4}/?', DocumentsPage),
    (r'/docs/?', DocumentsPage),
    (r'/d/\d{4}/?', DocumentsPage),
    (r'/d/?', DocumentsPage),
    (r'/kitofparts/?', KitOfPartsPage),
    (r'/k/?', KitOfPartsPage),
    (r'/updates/?', UpdatesPage),
    (r'/u/?', UpdatesPage),
    (r'/blog/?', BlogPage),
    (r'/b/?', BlogPage),
    (r'/forums?/?', ForumsPage),
    (r'/f/?', ForumsPage),
    (r'/qa?/?', QAPage),
    (r'/news/?', NewsPage),
    (r'/n/?', NewsPage),
    (r'/youtube/?', YouTubePage),
    (r'/y/?', YouTubePage),
    (r'/tims/?', TIMSPage),
    (r'/stims/?', STIMSPage),
    (r'/vims/?', VIMSPage),
    (r'/kickoff/?', KickoffPage),
    (r'/fmsdump/?', GetFRCSpyDump),
    (r'/ko/?', KickoffPage),
    (r'/calendar/?', CalendarPage),
    (r'/cal/?', CalendarPage),
    (r'/cookie/?', CookiePage),
    (r'/flushteams/?', FlushTeamsPage),
    (r'/scrapeteams/\d{4}/\d+/?', ScrapeTeamsPage),
    (r'/robots.txt', RobotsTxtPage),
    (r'/usfirst.org', ReferrerRedirectPage),
    ('.*', InstructionPage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
