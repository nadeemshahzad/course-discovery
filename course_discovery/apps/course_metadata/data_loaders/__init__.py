import abc

import html2text
from dateutil.parser import parse
from django.utils.functional import cached_property
from edx_rest_api_client.client import EdxRestApiClient
from opaque_keys.edx.keys import CourseKey

from course_discovery.apps.core.utils import delete_orphans
from course_discovery.apps.course_metadata.models import Image, Video


class AbstractDataLoader(metaclass=abc.ABCMeta):
    """ Base class for all data loaders.

    Attributes:
        api_url (str): URL of the API from which data is loaded
        partner (Partner): Partner which owns the data for this data loader
        access_token (str): OAuth2 access token
        PAGE_SIZE (int): Number of items to load per API call
    """

    PAGE_SIZE = 50
    SUPPORTED_TOKEN_TYPES = ('bearer', 'jwt',)

    def __init__(self, partner, api_url, access_token=None, token_type=None, max_workers=None):
        """
        Arguments:
            partner (Partner): Partner which owns the APIs and data being loaded
            api_url (str): URL of the API from which data is loaded
            access_token (str): OAuth2 access token
            token_type (str): The type of access token passed in (e.g. Bearer, JWT)
        """
        if token_type:
            token_type = token_type.lower()

            if token_type not in self.SUPPORTED_TOKEN_TYPES:
                raise ValueError('The token type {token_type} is invalid!'.format(token_type=token_type))

        self.access_token = access_token
        self.token_type = token_type
        self.partner = partner
        self.api_url = api_url.strip('/')

        self.max_workers = max_workers

    @cached_property
    def api_client(self):
        """
        Returns an authenticated API client ready to call the API from which data is loaded.

        Returns:
            EdxRestApiClient
        """
        kwargs = {}

        if self.token_type == 'jwt':
            kwargs['jwt'] = self.access_token
        else:
            kwargs['oauth_access_token'] = self.access_token

        return EdxRestApiClient(self.api_url, **kwargs)

    @abc.abstractmethod
    def ingest(self):  # pragma: no cover
        """ Load data for all supported objects (e.g. courses, runs). """
        pass

    @classmethod
    def clean_string(cls, s):
        """ Removes all leading and trailing spaces. Returns None if the resulting string is empty. """
        if not isinstance(s, str):
            return s

        return s.strip() or None

    @classmethod
    def clean_strings(cls, data):
        """ Iterates over all string values, removing leading and trailing spaces,
        and replacing empty strings with None. """
        return {k: cls.clean_string(v) for k, v in data.items()}

    @classmethod
    def clean_html(cls, content):
        """Cleans HTML from a string and returns a Markdown version."""
        stripped = content.replace('&nbsp;', '')
        html_converter = html2text.HTML2Text()
        html_converter.wrap_links = False
        html_converter.body_width = None
        return html_converter.handle(stripped).strip()

    @classmethod
    def parse_date(cls, date_string):
        """
        Returns a parsed date.

        Args:
            date_string (str): String to be parsed.

        Returns:
            datetime, or None
        """
        if date_string:
            return parse(date_string)

        return None

    @classmethod
    def get_course_key_from_course_run_key(cls, course_run_key):
        """
        Given a serialized course run key, return the corresponding
        serialized course key.

        Args:
            course_run_key (CourseKey): Course run key.

        Returns:
            str
        """
        return '{org}+{course}'.format(org=course_run_key.org, course=course_run_key.course)

    @classmethod
    def delete_orphans(cls):
        """ Remove orphaned objects from the database. """
        for model in (Image, Video):
            delete_orphans(model)

    @classmethod
    def _get_or_create_media(cls, media_type, url):
        media = None

        if url:
            media, __ = media_type.objects.get_or_create(src=url)

        return media

    @classmethod
    def get_or_create_video(cls, url, image_url=None):
        video = cls._get_or_create_media(Video, url)

        if video:
            image = cls.get_or_create_image(image_url)
            video.image = image
            video.save()

        return video

    @classmethod
    def get_or_create_image(cls, url):
        return cls._get_or_create_media(Image, url)
