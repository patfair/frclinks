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
Provides functions for caching and retrieving the location of FIRST team info
pages.
"""

import re

from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db

# Separates tpids on the FIRST list of all teams.
teamRe = re.compile(r'tpid=(\d+)[A-Za-z0-9=&;\-:]*?"><b>(\d+)')

class TeamTpid(db.Model):
  '''
  Stores a team number->tpid relationship for the most recent season the team was active.
  '''
  number = db.IntegerProperty()
  tpid = db.IntegerProperty()
  year = db.IntegerProperty()

def LookupTeam(number):
  '''
  Retrieves the tpid from the current season for a team.
  '''
  tpid = memcache.get(number, namespace="Team")
  if tpid == "null":
    return None
  if tpid is not None:
    return tpid
  team = TeamTpid.all().filter('number =', int(number)).fetch(1)
  if team:
    tpid = str(team[0].tpid)
    memcache.add(number, tpid, namespace="Team")
    return tpid

  # Cache the negative case to prevent spurious datastore lookups for old teams.
  memcache.add(number, "null", namespace="Team")

  return None

def ScrapeTeam(number, year):
  '''
  Searches the FIRST list of all teams for the requested team's tpid, caching
  all it encounters in the datastore.
  '''
  skip = 0
  while 1:
    scrapeDone = ScrapeTeams(year, skip)
    tpid = memcache.get(number, namespace="Team")
    if tpid and tpid != "null":
      return tpid
    if scrapeDone:
      return None
    skip += 250

def ScrapeTeams(year, start):
  '''
  Searches one page of the FIRST list of all teams for the given season, caching
  the tpid of all teams not already cached in the datastore. Returns true if
  there are no more pages of teams to scrape after this one.
  '''
  teamList = urlfetch.fetch(
      'https://my.usfirst.org/myarea/index.lasso?page=searchresults&' +
      'programs=FRC&reports=teams&sort_teams=number&results_size=250&' +
      'omit_searchform=1&season_FRC=' + year + '&skip_teams=' + str(start),
      deadline=10)
  teamResults = teamRe.findall(teamList.content)
  for teamResult in teamResults:
    teamNumber = int(teamResult[1])
    teamTpid = teamResult[0]
    teamQuery = TeamTpid.all().filter('number =', int(teamNumber))
    if teamQuery.count() == 0:
      # Insert a new record for the team.
      newTeam = TeamTpid()
      newTeam.number = int(teamNumber)
      newTeam.tpid = int(teamTpid)
      newTeam.year = int(year)
      newTeam.put()
      memcache.set(str(teamNumber), teamTpid, namespace="Team")
    elif teamQuery.filter('year <', int(year)).count() != 0:
      # Updated the existing team record if this tpid is more recent.
      team = teamQuery.fetch(1)[0]
      team.tpid = int(teamTpid)
      team.year = int(year)
      team.put()
      memcache.set(str(teamNumber), teamTpid, namespace="Team")
  return len(teamResults) < 250

def FlushTeams():
  '''
  Deletes 500 teams at a time from the datastore (Google limit).
  '''
  query = TeamTpid.all()
  entries = query.fetch(500)
  db.delete(entries)
  memcache.flush_all()
