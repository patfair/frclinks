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

# Extracts the link to the next page of results on the FIRST list of all teams.
lastPageRe = re.compile(r'Next ->')

# Extracts the FIRST team info page URL on the FIRST list of all teams.
oldTeamPageRe = re.compile(r'\?page=team_details[A-Za-z0-9=&;\-:]*')

class Team(db.Model):
  '''
  Stores a team number->tpid relationship for the current season.
  '''
  number = db.IntegerProperty()
  tpid = db.IntegerProperty()

class OldTeam(db.Model):
  '''
  Stores a team number->list rank relationship for a past season.
  '''
  number = db.IntegerProperty()
  year = db.IntegerProperty()
  rank = db.IntegerProperty()

def LookupTeam(number):
  '''
  Retrieves the tpid from the current season for a team.
  '''
  tpid = memcache.get(number, namespace="Team")
  if tpid == "null":
    return None
  if tpid is not None:
    return tpid
  team = Team.all().filter('number =', int(number)).fetch(1)
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
    teamList = urlfetch.fetch(
        'https://my.usfirst.org/myarea/index.lasso?page=searchresults&' +
        'programs=FRC&reports=teams&sort_teams=number&results_size=250&' +
        'omit_searchform=1&season_FRC=' + year + '&skip_teams=' + str(skip),
        deadline=10)
    teamResults = teamRe.findall(teamList.content)
    tpid = None
    for teamResult in teamResults:
      teamNumber = teamResult[1]
      teamTpid = teamResult[0]
      if teamNumber == number:
        tpid = teamTpid
      if Team.all().filter('number =', int(teamNumber)).count() == 0:
        newTeam = Team()
        newTeam.number = int(teamNumber)
        newTeam.tpid = int(teamTpid)
        newTeam.put()
        memcache.set(teamNumber, teamTpid, namespace="Team")
    if tpid:
      return tpid
    if len(lastPageRe.findall(teamList.content)) == 0:
      return None
    skip += 250

def FlushNewTeams():
  '''
  Deletes 500 teams at a time from the datastore (Google limit).
  '''
  query = Team.all()
  entries = query.fetch(500)
  db.delete(entries)
  memcache.flush_all()

def FlushOldTeams():
  '''
  Deletes 500 teams at a time from the datastore (Google limit).
  '''
  query = OldTeam.all()
  entries = query.fetch(500)
  db.delete(entries)
  memcache.flush_all()

def GetOldTeams(year, start):
  '''
  Searches the FIRST list of all teams for the given past season, caching the
  list rank of all teams not already cached in the datastore.
  '''
  rank = int(start)
  teamList = urlfetch.fetch(
      'https://my.usfirst.org/myarea/index.lasso?page=searchresults&' +
      'programs=FRC&reports=teams&sort_teams=number&results_size=250&' +
      'omit_searchform=1&season_FRC=' + year + '&skip_teams=' + str(rank),
      deadline=10)
  teamResults = teamRe.findall(teamList.content)
  for teamResult in teamResults:
    teamNumber = int(teamResult[1])
    teamCheck = Team.all().filter('number =', teamNumber).fetch(1)
    if not teamCheck:
      oldTeamCheck = OldTeam.all().filter('number =', teamNumber).fetch(1)
      if not oldTeamCheck:
        oldTeam = OldTeam()
        oldTeam.number = teamNumber
        oldTeam.year = int(year)
        oldTeam.rank = rank
        oldTeam.put()
    rank += 1

def LookupOldTeamPage(number):
  '''
  Retrieves the given team's FIRST info page URL using the year and rank in the
  datastore. Used to circumvent FIRST's requirement of a valid session token.
  '''
  team = memcache.get(number, namespace="OldTeam")
  if not team:
    team = OldTeam.all().filter('number =', int(number)).fetch(1)
    if not team:
      return None
    memcache.set(number, team, namespace="OldTeam")

  teamList = urlfetch.fetch(
      'https://my.usfirst.org/myarea/index.lasso?page=searchresults&' +
      'programs=FRC&reports=teams&sort_teams=number&results_size=1&' +
      'omit_searchform=1&season_FRC=' + str(team[0].year) + '&skip_teams=' +
      str(team[0].rank),
      deadline=10)
  teamPageUrl = oldTeamPageRe.findall(teamList.content)[0].replace('&amp;', '&')
  return 'https://my.usfirst.org/myarea/index.lasso' + teamPageUrl
