import urllib.parse
import hashlib
import json

from typing import Union, Dict

import trio
import asks
from asks.response_objects import Response

from spins_halp_line.constants import Credentials
from spins_halp_line.util import get_logger, SynchedCache

_cred_key = "resource_space"
_field_ids = {
    "adventure_name": 86,
    "player": 87
}

_base_url = "base_url"
_user = "user"
_secret = "secret"

_l = get_logger()

# search:
# [
# 	{
# 		"score":"0",
# 		"ref":"1001",
# 		"resource_type":"4",
# 		"has_image":"0",
# 		"is_transcoding":"0",
# 		"creation_date":"2020-11-18 19:13:51",
# 		"rating":"",
# 		"user_rating":"",
# 		"user_rating_count":"",
# 		"user_rating_total":"",
# 		"file_extension":"mp3",
# 		"preview_extension":"jpg",
# 		"image_red":"",
# 		"image_green":"",
# 		"image_blue":"",
# 		"thumb_width":"",
# 		"thumb_height":"",
# 		"archive":"0",
# 		"access":"0",
# 		"colour_key":"",
# 		"created_by":"1",
# 		"file_modified":"2020-11-18 19:13:51",
# 		"file_checksum":"",
# 		"request_count":"0",
# 		"new_hit_count":"8",
# 		"expiry_notification_sent":"0",
# 		"preview_tweaks":"0|1",
# 		"file_path":"",
# 		"modified":"2020-11-19 03:58:07",
# 		"group_access":"",
# 		"user_access":"",
# 		"field12":"2020-11-18 19:13",
# 		"field8":"Shipwreck Front Yard",
# 		"field3":"",
# 		"order_by":"",
# 		"total_hit_count":"8"
# 	}
# ]
# get_resource_data
# {
# 	"ref":"1001", // both
# 	"title":"", // not the title field in the ui lol
# 	"resource_type":"4", // both
# 	"has_image":"0", // both
# 	"is_transcoding":"0", // both
# 	"hit_count":"8",
# 	"new_hit_count":"8", // both
# 	"creation_date":"2020-11-18 19:13:51", // both
# 	"rating":"", // both
# 	"user_rating":"", // both
# 	"user_rating_count":"", // both
# 	"user_rating_total":"", // both
# 	"country":"",
# 	"file_extension":"mp3", // both
# 	"preview_extension":"jpg", // both
# 	"image_red":"", // both
# 	"image_green":"", // both
# 	"image_blue":"", // both
# 	"thumb_width":"", // both
# 	"thumb_height":"", // both
# 	"archive":"0", // both
# 	"access":"0", // both
# 	"colour_key":"", // both
# 	"created_by":"1", // both
# 	"file_path":"", // both
# 	"file_modified":"2020-11-18 19:13:51", // both
# 	"file_checksum":"", // both
# 	"request_count":"0", // both
# 	"expiry_notification_sent":"0", // both
# 	"preview_tweaks":"0|1", // both
# 	"geo_lat":"",
# 	"geo_long":"",
# 	"mapzoom":"",
# 	"disk_usage":"623803",
# 	"disk_usage_last_updated":"2020-11-18 19:13:52",
# 	"file_size":"623803",
# 	"preview_attempts":"1",
# 	"field12":"2020-11-18 19:13", // both (?)
# 	"field8":"Shipwreck Front Yard", // both (title)
# 	"field3":"", // both (?)
# 	"modified":"2020-11-19 03:58:07",
# 	"last_verified":"",
# 	"integrity_fail":"0",
# 	"google_vision_processed":"",
# 	"lock_user":""
# }

# Community boards are useful: https://groups.google.com/g/resourcespace?pli=1

# static cache
_global_cache = SynchedCache()

class RSResource(object):

    @classmethod
    async def for_room(cls, room_name):
        # https://www.resourcespace.com/knowledge-base/user/special-search-terms
        # todo: The caching logic here could use improvement. We cache the data from a particular room
        # todo: so if we load the same room again we won't repeat those requests...but it seems wrong to
        # todo: cache searches? This caching model is based on a read-only assumption - that the server
        # todo: will be restarted if we make changes in the CMS. Maybe we should cache search results?
        # todo: In any case, since these calls should mostly be made once, it's possible that any caching
        # todo: is properly viewed as premature optimization.
        files = await cls._get(
            'do_search',
            {
                'search': f'room:{room_name}'
            }
        )
        files = [f for f in files if f['field8'] == room_name]
        return await cls._from_list(files)

    @classmethod
    async def _from_list(cls, resources):
        result = []
        for r in resources:
            obj = RSResource(r)
            await obj.load()
            result.append(obj)

        return result


    _k_id = 'ref'
    _k_ext = 'file_extension'
    _k_ui_title = 'field8'
    _k_d_url = 'data_url'
    _k_adventure = 'adventure_name'
    _k_player = 'player'
    _k_room = 'room'
    _k_date = 'date'
    _k_duration = 'duration'
    _k_path = 'path'

    _extended_fields = [
        _k_adventure,
        _k_player,
        _k_room,
        _k_date,
        _k_duration,
        _k_path
    ]

    _resource_types = {
        '1': 'photo',
        '2': 'document',
        '3': 'video',
        '4': 'audio'
    }

    def __init__(self, data: Union[Dict[str,str], str, int]):
        global _global_cache
        self._cache = _global_cache
        self._data = {}
        self._loaded = False
        self._id = None
        if isinstance(data, dict):
            self._data = data
            self._loaded_basic = True
            # self._id = data.get(self._k_id)
        elif isinstance(data, int) or isinstance(data, str):
            self._id = int(data)

    def _throw_if_not_loaded(self):
        if not self._loaded:
            raise ValueError(f'{self} has not had its fields loaded!')

    async def load(self):
        cache_key = self.id

        # support caching results
        data = await self._cache.get(cache_key)
        if data is None:
            data = await self.get_info()
            data = await self.load_extended_fields(data)

            self._data = data
            # do this last so the extension is loaded
            data[self._k_d_url] = await self.get_data_url()

            await self._cache.set(cache_key, data)

        self._data = data
        self._loaded = True

    async def load_extended_fields(self, data):
        for field in (await self.get_all_fields()):
            name = field['name']

            if name in self._extended_fields:
                data[name] = field['value']

        return data

    @property
    def id(self):
        return self._data.get(self._k_id, self._id)

    @property
    def ext(self):
        return self._data.get(self._k_ext)

    @property
    def title(self):
        return self._data.get(self._k_ui_title)

    @property
    def url(self):
        return self._data.get(self._k_d_url)

    @property
    def adventure(self):
        return self._data.get(self._k_adventure)

    @property
    def player(self):
        return self._data.get(self._k_player)

    @property
    def room(self):
        return self._data.get(self._k_room)

    @property
    def date(self):
        return self._data.get(self._k_date)

    @property
    def duration(self):
        return self._data.get(self._k_duration)

    @property
    def path(self):
        return self._data.get(self._k_path)

    async def get_data_url(self):
        return await self._get(
            'get_resource_path',
            {
                'ref': self.id,
                'getfilepath': 0,
                'extension': self.ext,
                # 'generate': True,
                # 'alternative': -1,
                # 'size': ''
            }
        )

    async def get_info(self):

        return await self._get(
            'get_resource_data',
            {
                'resource': self.id
            }
        )

    # Example response JSON:
    # [
    #     {"value": "Shipwreck Adventure", "resource_type_field": "86", "ref": "86", "name": "adventure_name",
    #      "title": "Adventure Name", "field_constraint": "0", "type": "3", "order_by": "0", "keywords_index": "1",
    #      "partial_index": "0", "resource_type": "0", "resource_column": "", "display_field": "1",
    #      "use_for_similar": "1", "iptc_equiv": "", "display_template": "", "tab_name": "", "required": "0",
    #      "smart_theme_name": "", "exiftool_field": "", "advanced_search": "1", "simple_search": "0", "help_text": "",
    #      "display_as_dropdown": "0", "external_user_access": "1", "autocomplete_macro": "", "hide_when_uploading": "0",
    #      "hide_when_restricted": "0", "value_filter": "", "exiftool_filter": "", "omit_when_copying": "0",
    #      "tooltip_text": "", "regexp_filter": "", "sync_field": "", "display_condition": "", "onchange_macro": "",
    #      "linked_data_field": "", "automatic_nodes_ordering": "0", "fits_field": "", "personal_data": "0",
    #      "include_in_csv_export": "1", "browse_bar": "1", "read_only": "0", "active": "1", "full_width": "0",
    #      "frequired": "0", "fref": "86"},
    #     {"value": "", "resource_type_field": "87", "ref": "87", "name": "player", "title": "Player",
    #      "field_constraint": "0", "type": "0", "order_by": "0", "keywords_index": "1", "partial_index": "0",
    #      "resource_type": "0", "resource_column": "", "display_field": "1", "use_for_similar": "1", "iptc_equiv": "",
    #      "display_template": "", "tab_name": "", "required": "0", "smart_theme_name": "", "exiftool_field": "",
    #      "advanced_search": "1", "simple_search": "0", "help_text": "", "display_as_dropdown": "0",
    #      "external_user_access": "1", "autocomplete_macro": "", "hide_when_uploading": "0", "hide_when_restricted": "0",
    #      "value_filter": "", "exiftool_filter": "", "omit_when_copying": "0", "tooltip_text": "", "regexp_filter": "",
    #      "sync_field": "", "display_condition": "", "onchange_macro": "", "linked_data_field": "",
    #      "automatic_nodes_ordering": "0", "fits_field": "", "personal_data": "0", "include_in_csv_export": "1",
    #      "browse_bar": "1", "read_only": "0", "active": "1", "full_width": "0", "frequired": "0", "fref": "87"},
    #     {"value": "Shipwreck Yard Front", "resource_type_field": "88", "ref": "88", "name": "room", "title": "Room",
    #      "field_constraint": "", "type": "3", "order_by": "0", "keywords_index": "1", "partial_index": "0",
    #      "resource_type": "0", "resource_column": "", "display_field": "1", "use_for_similar": "1", "iptc_equiv": "",
    #      "display_template": "", "tab_name": "", "required": "0", "smart_theme_name": "", "exiftool_field": "",
    #      "advanced_search": "1", "simple_search": "0", "help_text": "", "display_as_dropdown": "0",
    #      "external_user_access": "1", "autocomplete_macro": "", "hide_when_uploading": "0", "hide_when_restricted": "0",
    #      "value_filter": "", "exiftool_filter": "", "omit_when_copying": "0", "tooltip_text": "", "regexp_filter": "",
    #      "sync_field": "", "display_condition": "", "onchange_macro": "", "linked_data_field": "",
    #      "automatic_nodes_ordering": "0", "fits_field": "", "personal_data": "0", "include_in_csv_export": "1",
    #      "browse_bar": "1", "read_only": "0", "active": "1", "full_width": "0", "frequired": "0", "fref": "88"},
    #     {"value": "Description", "resource_type_field": "8", "ref": "8", "name": "title", "title": "Title",
    #      "field_constraint": "", "type": "0", "order_by": "10", "keywords_index": "1", "partial_index": "0",
    #      "resource_type": "0", "resource_column": "title", "display_field": "0", "use_for_similar": "1",
    #      "iptc_equiv": "2#005", "display_template": "", "tab_name": "", "required": "1", "smart_theme_name": "",
    #      "exiftool_field": "Title", "advanced_search": "1", "simple_search": "0", "help_text": "",
    #      "display_as_dropdown": "0", "external_user_access": "1", "autocomplete_macro": "", "hide_when_uploading": "0",
    #      "hide_when_restricted": "0", "value_filter": "", "exiftool_filter": "", "omit_when_copying": "",
    #      "tooltip_text": "", "regexp_filter": "", "sync_field": "", "display_condition": "", "onchange_macro": "",
    #      "linked_data_field": "", "automatic_nodes_ordering": "0", "fits_field": "", "personal_data": "0",
    #      "include_in_csv_export": "1", "browse_bar": "1", "read_only": "0", "active": "1", "full_width": "0",
    #      "frequired": "1", "fref": "8"},
    #     ...
    # ]

    async def get_all_fields(self):
        return await self._get(
            'get_resource_field_data',
            {
                'resource': self.id
            }
        )

    def _add_extended_field(self, field):
        self._data[field['name']] = field['']

    @staticmethod
    async def _get(function, params, unwrap=True) -> dict:
        base_url = Credentials[_cred_key][_base_url]

        params['function'] = function
        params['user'] = Credentials[_cred_key][_user]
        qstring = urllib.parse.urlencode(params)

        secret = Credentials[_cred_key][_secret]
        signer = hashlib.sha256()
        signer.update(f'{secret}{qstring}'.encode("utf-8"))

        request = f'{base_url}?{qstring}&sign={signer.hexdigest()}'
        result: Response = await asks.get(request)
        # print("-" * 60)
        # print(request)
        # print(">" * 5)
        # print(result)
        # print("\\/" * 5)
        # print(result.content.decode("utf-8"))
        # print("-" * 60)

        # if unwrap and result.status_code >= 200 and result.status_code < 300:
        result: dict = json.loads(result.content.decode("utf-8"))

        return result

    def __str__(self):
        return f'RSR[{self.id}] {self.url}'

    def __repr__(self):
        return str(self)


# def _check_creds():
#     global _cred_key
#     if _cred_key not in Credentials:
#         return False
#
#     return True
#
# async def _do_get(function, params):
#     if not _check_creds():
#         _l.error(f"Do not have credentials loaded for {_cred_key}")
#         return {}
#
#     base_url = Credentials[_cred_key][_base_url]
#
#     params['function'] = function
#     params['user'] = Credentials[_cred_key][_user]
#     qstring = urllib.parse.urlencode(params)
#
#     secret = Credentials[_cred_key][_secret]
#     print(secret)
#     print(qstring)
#     signer = hashlib.sha256()
#     signer.update(f'{secret}{qstring}'.encode("utf-8"))
#
#     request = f'{base_url}?{qstring}&sign={signer.hexdigest()}'
#     result = await asks.get(request)
#     # print("-" * 60)
#     # print(request)
#     # print(">" * 5)
#     # print(result)
#     # print("\\/" * 5)
#     # print(result.content.decode("utf-8"))
#     # print("-" * 60)
#     return result
#
#
#
# async def search(term) -> Response:
#     return await _do_get(
#         'do_search',
#         {
#             'search': term
#         }
#     )
#
# async def get_resource_field_data(id) -> Response:
#     return await _do_get(
#         'get_resource_field_data',
#         {
#             'resource': id
#         }
#     )
#
# async def get_resource_data(id) -> Response:
#     return await _do_get(
#         'get_resource_data',
#         {
#             'resource': id
#         }
#     )
#
# # https://profspins.free.resourcespace.com/pages/download.php?ref=1001&size=&ext=mp3&k=&alternative=-1&usage=-1&usagecomment=
# async def get_url(id, extension = "mp3") -> Response:
#     # https://www.resourcespace.com/knowledge-base/api/get_resource_path
#     # note: the $resource argument is actually called $ref
#     return await _do_get(
#         'get_resource_path',
#         {
#             'ref': id,
#             'getfilepath': 0,
#             'extension': extension,
#             # 'generate': True,
#             # 'alternative': -1,
#             # 'size': ''
#         }
#     )