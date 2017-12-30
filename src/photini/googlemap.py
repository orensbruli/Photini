# -*- coding: utf-8 -*-
##  Photini - a simple photo metadata editor.
##  http://github.com/jim-easterbrook/Photini
##  Copyright (C) 2012-17  Jim Easterbrook  jim@jim-easterbrook.me.uk
##
##  This program is free software: you can redistribute it and/or
##  modify it under the terms of the GNU General Public License as
##  published by the Free Software Foundation, either version 3 of the
##  License, or (at your option) any later version.
##
##  This program is distributed in the hope that it will be useful,
##  but WITHOUT ANY WARRANTY; without even the implied warranty of
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
##  General Public License for more details.
##
##  You should have received a copy of the GNU General Public License
##  along with this program.  If not, see
##  <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import locale
import os
import re
import webbrowser

import requests

from photini.configstore import key_store
from photini.photinimap import PhotiniMap
from photini.pyqt import Busy, QtCore, QtWidgets

class GoogleMap(PhotiniMap):
    def __init__(self, *arg, **kw):
        super(GoogleMap, self).__init__(*arg, **kw)
        self.api_key = key_store.get('google', 'api_key')

    def get_page_elements(self):
        url = 'http://maps.googleapis.com/maps/api/js?callback=initialize&v=3'
        if self.app.test_mode:
            url += '.exp'
        url += '&key=' + self.api_key
        lang, encoding = locale.getdefaultlocale()
        if lang:
            match = re.match('[a-zA-Z]+[-_]([A-Z]+)', lang)
            if match:
                name = match.group(1)
                if name:
                    url += '&region=' + name
        return {
            'head': '',
            'body': '''
    <script type="text/javascript"
      src="{}" async defer>
    </script>
'''.format(url),
            }

    def show_terms(self):
        # return widget to display map terms and conditions
        layout = QtWidgets.QVBoxLayout()
        widget = QtWidgets.QLabel(self.tr('Search powered by Google'))
        widget.setStyleSheet('QLabel { font-size: 10px }')
        layout.addWidget(widget)
        widget = QtWidgets.QPushButton(self.tr('Terms of Use'))
        widget.clicked.connect(self.load_tou)
        widget.setStyleSheet('QPushButton { font-size: 10px }')
        layout.addWidget(widget)
        return layout

    @QtCore.pyqtSlot()
    def load_tou(self):
        webbrowser.open_new('http://www.google.com/help/terms_maps.html')

    def do_search(self, params):
        self.disable_search()
        params['key'] = self.api_key
        lang, encoding = locale.getdefaultlocale()
        if lang:
            params['language'] = lang
        url = 'https://maps.googleapis.com/maps/api/geocode/json'
        with Busy():
            try:
                rsp = requests.get(url, params=params, timeout=5)
            except Exception as ex:
                self.logger.error(str(ex))
                return []
        if rsp.status_code >= 400:
            self.logger.error('Search error %d', rsp.status_code)
            return []
        self.enable_search()
        rsp = rsp.json()
        if rsp['status'] != 'OK':
            if 'error_message' in rsp:
                self.logger.error(
                    'Search error: %s: %s', rsp['status'], rsp['error_message'])
            else:
                self.logger.error('Search error: %s', rsp['status'])
            return []
        results = rsp['results']
        if not results:
            self.logger.error('No results found')
            return []
        return results

    address_map = {
        'world_region'  : ('no_key',),
        'country_code'  : ('country_code',),
        'country_name'  : ('country',),
        'province_state': ('administrative_area_level_3',
                           'administrative_area_level_2',
                           'administrative_area_level_1'),
        'city'          : ('sublocality_level_2', 'sublocality_level_1',
                           'sublocality', 'neighborhood', 'locality',
                           'postal_town'),
        'sublocation'   : ('establishment', 'point_of_interest', 'premise',
                           'street_number', 'route'),
        }

    def reverse_geocode(self, coords):
        results = self.do_search({'latlng': coords})
        if not results:
            return
        # the first result is the most specific
        address_components = results[0]['address_components']
        # merge in a street address if it's not the first result
        for result in results[1:]:
            if 'street_address' in result['types']:
                address_components += result['address_components']
        address = {}
        for item in address_components:
            type_name = ''
            for name in item['types']:
                if name == 'political':
                    continue
                if len(name) > len(type_name):
                    type_name = name
            if not type_name:
                type_name = 'unknown'
            if type_name in ('postal_code', 'postal_code_suffix'):
                continue
            address[type_name] = item['long_name']
            if type_name == 'country':
                address['country_code'] = item['short_name']
        return address

    @QtCore.pyqtSlot()
    def search(self, search_string=None):
        if not search_string:
            search_string = self.edit_box.lineEdit().text()
            self.edit_box.clearEditText()
        if not search_string:
            return
        self.search_string = search_string
        self.clear_search()
        north, east, south, west = self.map_status['bounds']
        params = {
            'address': search_string,
            'bounds' : '{!r},{!r}|{!r},{!r}'.format(south, west, north, east),
            }
        results = self.do_search(params)
        for result in results:
            bounds = result['geometry']['viewport']
            self.search_result(
                bounds['northeast']['lat'], bounds['northeast']['lng'],
                bounds['southwest']['lat'], bounds['southwest']['lng'],
                result['formatted_address'])
