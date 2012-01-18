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

import os
import re
import urllib

from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from team import FlushNewTeams
from team import FlushOldTeams
from team import GetOldTeams
from team import LookupOldTeamPage
from team import LookupTeam
from team import ScrapeTeam

# Extracts the team number from the end of the URL.
numberRe = re.compile(r'\d+')

# Extracts the area code from the end of the URL.
areaRe = re.compile(r'[A-Za-z\-]+')

# Extracts the event code from the end of the URL.
eventRe = re.compile(r'[A-Za-z]+\d?')

# Extracts the year from the end of the URL.
yearRe = re.compile(r'\d{4}')

# Extracts the team webpage from the FIRST team info page.
websiteRe = re.compile(r'href="http://[A-Za-z0-9\.\-_/#]+')

# Extracts old team scrape parameters.
oldTeamRe = re.compile(r'(\d{4})/(\d+)')

# Extracts the requested manual section.
sectionRe = re.compile(r'/([iagrt])')

# Extracts a session code.
sessionRe = re.compile(r'session=myarea:([A-Za-z0-9]+)')

# Year to default to for event information if none is provided.
defaultYear = '2012'

# Base url for many FRC pages.
frcUrl = 'http://www.usfirst.org/roboticsprograms/frc/'

# Mapping of years to year-specific pages.
regionalYears = {'default':frcUrl + 'regionalevents.aspx?id=430',
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
                     '2011':frcUrl + 'content.aspx?id=432',  # No page exists.
                     '2010':frcUrl + 'content.aspx?id=432',  # No page exists.
                     '2009':frcUrl + 'content.aspx?id=14716',
                     '2008':frcUrl + 'content.aspx?id=11286',
                     '2007':frcUrl + 'content.aspx?id=6778',
                     '2006':frcUrl + 'content.aspx?id=4188',
                     '2005':frcUrl + 'content.aspx?id=4388',
                     '2004':frcUrl + 'content.aspx?id=9302',
                     '2003':frcUrl + 'content.aspx?id=9304',}
documentsYears = {'default':frcUrl + 'content.aspx?id=4094',
                  '2012':frcUrl + 'competition-manual-and-related-documents',
                  '2011':frcUrl + '2011-competition-manual-and-related-documents',
                  '2010':frcUrl + 'content.aspx?id=18068',
                  '2009':frcUrl + 'content.aspx?id=15523',
                  '2008':frcUrl + 'content.aspx?id=9152',
                  '2007':frcUrl + 'content.aspx?id=7430',
                  '2006':frcUrl + 'content.aspx?id=3630',}
documentsSections = {'i':'30',
                     'a':'55',
                     'g':'56',
                     'r':'57',
                     't':'58',}

def GetYear(handler):
  endNumber = yearRe.findall(handler.request.path)
  if len(endNumber) > 0:
    return endNumber[-1]
  else:
    return defaultYear

def GetEvent(handler):
  event = eventRe.findall(handler.request.path)[-1]
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

    # First, try checking the datastore for the current season`s tpid. 
    tpid = LookupTeam(team)
    if tpid:
      return ('https://my.usfirst.org/myarea/index.lasso?page=team_details' +
                    '&tpid=' + tpid)

    # Second, try checking the datastore for a past season`s URL.
    teamPageUrl = LookupOldTeamPage(team)
    if teamPageUrl:
      return teamPageUrl

    # Third, try scraping the FIRST website for the current season`s tpid.
    tpid = ScrapeTeam(team, defaultYear)
    if tpid:
      return ('https://my.usfirst.org/myarea/index.lasso?page=team_details' +
                    '&tpid=' + tpid)

    return None

def Redir(handler, url):
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
        Redir(self, website[0][6:])

class TeamTheBlueAlliancePage(webapp.RequestHandler):
  """
  Redirects the user to the given team's The Blue Alliance page.
  """
  def get(self):
    team = numberRe.findall(self.request.path)[-1]
    Redir(self, 'http://www.thebluealliance.com/team/' + team)

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
    event = eventRe.findall(self.request.path)[-1]
    year = GetYear(self)
    
    # Do some special case handling for on/on2 in 2012 because FIRST is broken.
    if year == '2012' and event == 'on' or event == 'on2':
      if event == 'on':
        code = '7641'
      else:
        code = '7697'

      eventsPage = urlfetch.fetch('https://my.usfirst.org/myarea/index.lasso?event_type=FRC')
      session = sessionRe.search(eventsPage.content).group(1)
      Redir(self, 'https://my.usfirst.org/myarea/index.lasso?page=event_teamlist&eid=' + code +
                    '&sort_teams=number&-session=myarea:' + session)
      return

    if event == 'arc':
      event = 'cmp&division=archimedes'
    elif event == 'cur':
      event = 'cmp&division=curie'
    elif event == 'gal':
      event = 'cmp&division=galileo'
    elif event == 'new':
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

class EventTheBlueAlliancePage(webapp.RequestHandler):
  """
  Redirects the user to the The Blue Alliance page for the given event.
  """
  def get(self):
    event = eventRe.findall(self.request.path)[-1]
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

class DocumentsSectionPage(webapp.RequestHandler):
  """
  Redirects the user to the requested section of the Competition Manual.
  """
  def get(self):
    sectionNumber = documentsSections[sectionRe.findall(self.request.path)[-1]]
    Redir(self, 'http://frc-manual.usfirst.org/viewItem/' + sectionNumber)

class UpdatesPage(webapp.RequestHandler):
  """
  Redirects the user to the Team Updates page.
  """
  def get(self):
    Redir(self, 'http://frc-manual.usfirst.org/TeamUpdates/0')

class BlogPage(webapp.RequestHandler):
  """
  Redirects the user to Bill's Blog.
  """
  def get(self):
    Redir(self, 'http://frcdirector.blogspot.com')

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

class CookiePage(webapp.RequestHandler):
  """
  ???
  """
  def get(self):
    Redir(self, 'http://www.chiefdelphi.com/media/photos/33801')

class FlushNewTeamsPage(webapp.RequestHandler):
  """
  Deletes 500 teams at a time from the datastore (Google limit).
  Unlisted on the instructions page; intended for admin use.
  """
  def get(self):
    FlushNewTeams()
    path = 'templates/instructions.html'
    self.response.out.write(template.render(path, {}))

class FlushOldTeamsPage(webapp.RequestHandler):
  """
  Deletes 500 teams at a time from the datastore (Google limit).
  Unlisted on the instructions page; intended for admin use.
  """
  def get(self):
    FlushOldTeams()
    path = 'templates/instructions.html'
    self.response.out.write(template.render(path, {}))

class GetOldTeamsPage(webapp.RequestHandler):
  """
  Retrieves and caches teams from the given year in the datastore.
  Unlisted on the instructions page; intended for admin use.
  """
  def get(self):
    oldTeamMatch = oldTeamRe.findall(self.request.path)
    GetOldTeams(oldTeamMatch[-1][0], oldTeamMatch[-1][1])
    path = 'templates/instructions.html'
    self.response.out.write(template.render(path, {}))

class InstructionPage(webapp.RequestHandler):
  """
  Displays the complete list of commands for this application.
  """
  def get(self):
    path = 'templates/instructions.html'
    self.response.out.write(template.render(path, {}))

class RobotsTxtPage(webapp.RequestHandler):
  """
  Displays the robots.txt file.
  """
  def get(self):
    self.response.headers.add_header('content-type', 'text/plain')
    self.response.out.write('User-agent: *\nDisallow:')

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
    (r'/d/[iagrt]/?', DocumentsSectionPage),
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
    (r'/cookie/?', CookiePage),
    (r'/flushnewteams/?', FlushNewTeamsPage),
    (r'/flusholdteams/?', FlushOldTeamsPage),
    (r'/getoldteams/\d{4}/\d+/?', GetOldTeamsPage),
    (r'/robots.txt', RobotsTxtPage),
    ('.*', InstructionPage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == "__main__":
  main()
