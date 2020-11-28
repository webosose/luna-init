#!/usr/bin/env python3
# Copyright (c) 2014-2020 LG Electronics, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
# LICENSE@@@

import sys, os.path, os
from getopt import gnu_getopt as getopt
from datetime import datetime
from itertools import *
import pytz
import json
from abbrevs import abbrevs

standard_year = datetime.utcnow().year

def supplementOmittedTimeZones():
	# pytz package keeps own timezone list
	# New timezone might be omitted if pytz version is old.
	# pytz.country_timezones() refers all_timezones_set and all_timezones
	for requiredZone in uiInfo:
		if requiredZone not in pytz.all_timezones_set:
			sys.stderr.write("Timezone %s is unknown in current pytz ver. Supplmented\n" % requiredZone)
			pytz.all_timezones_set.add(requiredZone)
			pytz.all_timezones.append(requiredZone)

		# America/Montreal was removed in zone.tab after September, 2013.
		# This means that pytz.country_timezones doesn't include Montreal.
		# Please refer http://en.wikipedia.org/wiki/America/Montreal
		# tzdata for Montreal is still supported for backward compatibility.
		# But, there is no information about that Montreal is in CA. So hard-coded.
		if requiredZone == 'America/Montreal' and requiredZone not in pytz.country_timezones['CA']:
			pytz.country_timezones['CA'].append('America/Montreal')

		if requiredZone == 'America/Godthab' and requiredZone not in pytz.country_timezones['GL']:
			pytz.country_timezones['GL'].append('America/Godthab')

	return

def findDST(tz):
	months = [datetime(standard_year, n+1, 1) for n in range(12)]
	try:
		std = next(dropwhile(lambda m: tz.dst(m).seconds != 0, months))
	except StopIteration: # next raises this if empty list
		raise Exception("Standard time should be present in any time-zone (even in %s)" % (tz))
	summer = next(chain(dropwhile(lambda m: tz.dst(m).seconds == 0, months), [None]))
	return (std, summer)

def genTimeZones(do_guess = True):
	for (cc, zoneIds) in list(pytz.country_timezones.items()):
		for zoneId in zoneIds:
			tz = pytz.timezone(zoneId)
			try:
				(std, summer) = findDST(tz)
			except Exception as e:
				sys.stderr.write("Exception: %s\n  Do some magic for %s\n" % (e, tz))
				std = datetime(datetime.utcnow().year, 1, 1)
				if tz.dst(std).seconds != 0: summer = std
				else: summer = None
			except StopIteration:
				raise Exception("Unexpected StopIteration")

			# use Country from tzdata
			country = pytz.country_names[cc]

			info = uiInfo.get(zoneId, None)
			if info is None:
				if not do_guess:
					# so we shouldn't try to guess?
					# lets skip unknown time-zones
					continue
				# guess City
				(zregion, zpoint) = zoneId.split('/',1)
				if zpoint != country: city = zpoint.replace('_',' ')
				else: city = ''
				# guess Description
				tzname = tz.tzname(std)
				description = abbrevs.get(tzname, tzname)
				preferred = False
			else:
				country = info.get('Country', country) # allow override
				city = info['City']
				description = info['Description']
				preferred = info.get('preferred', False)

			entry = {
				'Country': country,
				'CountryCode': cc,
				'ZoneID': zoneId,
				'supportsDST': 0 if summer is None else 1,
				'offsetFromUTC': int(tz.utcoffset(std).total_seconds()/60),
				'Description': description,
				'City': city
			}
			if preferred: entry['preferred'] = True
			yield entry

def genSysZones():
	for offset in takewhile(lambda x: x < 12.5, count(-14, 0.5)):
		offset_str = str(abs(int(offset)))
		if offset != int(offset): offset_str = offset_str + ":30"
		if offset > 0: ids = [('Etc/GMT+%s' % offset_str, 'GMT-%s' % offset_str)]
		elif offset < 0: ids = [('Etc/GMT-%s' % offset_str, 'GMT+%s' % offset_str)]
		else: ids = [('Etc/' + x, 'GMT') for x in ['GMT-0', 'GMT+0']]
		for (zoneId, id) in ids:
			yield {
				'Country': '',
				'CountryCode': '',
				'ZoneID': zoneId,
				'supportsDST': 0,
				'offsetFromUTC': int(-offset*60),
				'Description': id,
				'City': ''
			}

### Parse options

output = None
source_dir = os.path.curdir
is_zoneinfo_default = True

def set_zoneinfo_dir(zoneinfo_dir):
	global is_zoneinfo_default
	is_zoneinfo_default = False
	def resource_path(name):
		if os.path.isabs(name):
			raise ValueError('Bad path (absolute): %r' % name)
		name_parts = os.path.split(name)
		for part in name_parts:
			if part == os.path.pardir:
				raise ValueError('Bad path segment: %r' % part)
		filepath = os.path.join(zoneinfo_dir, *name_parts)
		return filepath
	pytz.open_resource = lambda name: open(resource_path(name), 'rb')
	pytz.resource_exists = lambda name: os.path.exists(resource_path(name))


opts, args = getopt(sys.argv[1:], 'z:o:s:w:y:', longopts=[
	'zoneinfo-dir=', 'output=', 'source-dir=', 'no-guess', 'white-list-only',
	'standard-year='
	])

do_guess = True

for (opt, val) in opts:
	if opt in ('--zoneinfo-dir', '-z'): set_zoneinfo_dir(val)
	elif opt in ('--output', '-o'): output = val
	elif opt in ('--source-dir', '-s'): source_dir = val
	elif opt in ('--no-guess', '--white-list-only', '-w'): do_guess = False
	elif opt in ('--standard-year', '-y'): standard_year = int(val) if val.isdigit() else standard_year

# openembedded sets some env variables. lets guess from one of it where is our sysroot.
guess_sysroot = os.environ.get('PKG_CONFIG_SYSROOT_DIR')
if guess_sysroot is not None and is_zoneinfo_default:
	set_zoneinfo_dir(os.path.join(guess_sysroot, 'usr', 'share', 'zoneinfo'))


### load reference files
mccInfo = json.load(open(os.path.join(source_dir, 'mccInfo.json'), 'r'))
uiInfo = json.load(open(os.path.join(source_dir, 'uiTzInfo.json'), 'r'))

### check available timezones in pytz library
supplementOmittedTimeZones()

### load natural timezones from pytz
timeZones = list(genTimeZones(do_guess = do_guess))
timeZones.sort(key = (lambda x: x['offsetFromUTC']))

# gen Etc/* time-zones
sysZones = list(genSysZones())

content = {
	'timeZone': timeZones,
	'syszones': sysZones,
	'mmcInfo': mccInfo
}

if output is None:
	import re
	s = json.dumps(content, ensure_ascii = False, indent = 2)
	s = re.sub(r'\s+$', '', s, flags = re.MULTILINE) + '\n'
	sys.stdout.write(s.encode('utf8'))
else:
	s = json.dumps(content, ensure_ascii = False, indent = None, separators = (',', ':')) + '\n'
	open(output,'wb').write(s.encode('utf8'))
