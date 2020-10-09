import logging
import time

from celery import chord
from django.core.management.base import BaseCommand

from enterprise_catalog.apps.api.tasks import (
    update_catalog_metadata_task,
    update_full_content_metadata_task,
)
from enterprise_catalog.apps.catalog.constants import COURSE
from enterprise_catalog.apps.catalog.management.utils import (
    get_all_content_keys,
)
from enterprise_catalog.apps.catalog.models import CatalogQuery


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Updates Content Metadata, along with the associations of Catalog Queries and Content Metadata. '
        'Example usage with --catalog_uuids: '
        './manage.py update_content_metadata --catalog_uuids {catalog_uuid_a} {catalog_uuid_b} ...'
    )

    def _run_update_catalog_metadata_task(self, catalog_query):
        message = (
            'Spinning off update_catalog_metadata_task from update_content_metadata command'
            ' to update content_metadata for catalog query %s.'
        )
        logger.info(message, catalog_query)
        return update_catalog_metadata_task.s(catalog_query_id=catalog_query.id)

    def _run_update_full_content_metadata_task(self, *args, **kwargs):
        """
        Runs the `update_full_content_metadata` for all content keys.

        Note that the keys get filtered down to course content keys inside the task.
        """
        message = (
            'Spinning off update_full_content_metadata_task from update_content_metadata command'
            ' to replace minimal json_metadata from /search/all/ with full json_metadata from /courses/.'
        )
        logger.info(message)

        all_content_keys = get_all_content_keys()
        # task.si() is used as a shortcut for an immutable signature to avoid calling this with the results from the
        # previously run `update_catalog_metadata_task`.
        # https://docs.celeryproject.org/en/master/userguide/canvas.html#immutability
        return update_full_content_metadata_task.si(all_content_keys)

    def handle(self, *args, **options):
        # find all CatalogQuery records used by at least one EnterpriseCatalog to avoid
        # calling /search/all/ for a CatalogQuery that is not currently used by any catalogs.
        catalog_queries = CatalogQuery.objects.filter(enterprise_catalogs__isnull=False).distinct()

        # create a group of celery tasks that run in parallel to create/update ContentMetadata records
        # and associate those with the appropriate CatalogQuery(s). once all those tasks succeed, run a
        # callback to update the json_metadata of ContentMetadata records with content type "course"
        # with the full course metadata from /courses/.
        result = chord(
            [
                self._run_update_catalog_metadata_task(catalog_query)
                for catalog_query in catalog_queries
            ]
        )(self._run_update_full_content_metadata_task())

        # Wait for the task to finish before the command returns,
        # but do not wait more than 30 minutes.
        max_wait_seconds = 30 * 60
        seconds_waited = 0
        interval_in_seconds = 10
        while not result.ready():
            time.sleep(interval_in_seconds)
            seconds_waited += interval_in_seconds
            if seconds_waited >= max_wait_seconds:
                logger.error('The command took longer than {} seconds to be ready.'.format(max_wait_seconds))
                break

        logger.info('Waited about {} total seconds for the async tasks to complete.'.format(seconds_waited))
        if result.ready() and result.successful():
            message = (
                'ContentMetadata records were successfully associated with their respective'
                ' CatalogQuery(s) and ContentMetadata records with content type of "%s" were'
                ' updated to include full course metadata.'
            )
            logger.info(message, COURSE)
        else:
            message = (
                'Could not successfully complete all async tasks spun off from the command. Check'
                ' the stack trace above for more details.'
            )
            logger.error(message)
