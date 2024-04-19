import datetime
import os
import json
import sqlite3
from contextlib import closing

import caldav
import pytest
import keyring
from decouple import config

import taskbridge.helpers as helpers
from taskbridge.reminders.model import reminderscript
from taskbridge.reminders.model.remindercontainer import ReminderContainer, LocalList, RemoteCalendar
from taskbridge.reminders.model.reminder import Reminder
from taskbridge.reminders.controller import ReminderController

TEST_ENV = config('TEST_ENV', default='remote')


class TestReminderContainer:

    @staticmethod
    def __connect_caldav():
        conf_file = helpers.settings_folder() / 'conf.json'
        if not os.path.exists(conf_file):
            assert False, "Failed to load configuration file."
        with open(helpers.settings_folder() / 'conf.json', 'r') as fp:
            settings = json.load(fp)

        ReminderController.CALDAV_USERNAME = settings['caldav_username']
        ReminderController.CALDAV_URL = settings['caldav_url']
        ReminderController.CALDAV_HEADERS = {}
        ReminderController.CALDAV_PASSWORD = keyring.get_password("TaskBridge", "CALDAV-PWD")
        ReminderController.TO_SYNC = settings['reminder_sync']
        ReminderController.connect_caldav()

    @staticmethod
    def __create_reminder_from_local() -> Reminder:
        uuid = "x-apple-id://1234-5678-9012"
        name = "Test reminder"
        created_date = "Thursday, 18 April 2024 at 08:00:00"
        completed = 'false'
        due_date = "Thursday, 18 April 2024 at 18:00:00"
        all_day = 'false'
        remind_me_date = "Thursday, 18 April 2024 at 18:00:00"
        modified_date = "Thursday, 18 April 2024 at 17:50:00"
        completion = 'missing value'
        body = "Test reminder body."

        values = [uuid, name, created_date, completed, due_date, all_day, remind_me_date, modified_date, completion, body]
        reminder = Reminder.create_from_local(values)
        return reminder

    # noinspection SpellCheckingInspection
    @staticmethod
    def __create_reminder_from_remote() -> Reminder:
        obj = caldav.CalendarObjectResource()
        # noinspection PyUnresolvedReferences
        obj._set_data("""BEGIN:VCALENDAR
    VERSION:2.0
    PRODID:-//Nextcloud Tasks v0.15.0
    BEGIN:VTODO
    CREATED:20240418T084019
    DESCRIPTION:Test reminder body
    DTSTAMP:20240418T084042
    DUE:20240418T180000
    LAST-MODIFIED:20240418T084042
    SUMMARY:Test reminder
    UID:f4a682ac-86f2-4f81-a08e-ccbff061d7da
    END:VTODO
    END:VCALENDAR
    """)
        reminder = Reminder.create_from_remote(obj)
        return reminder

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires CalDAV credentials")
    def test_load_caldav_calendars(self):
        TestReminderContainer.__connect_caldav()
        remote_calendars = ReminderContainer.load_caldav_calendars()
        assert len(remote_calendars) > 0

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud")
    def test_load_local_lists(self):
        local_lists = ReminderContainer.load_local_lists()
        assert len(local_lists) > 0

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud")
    def test_count_local_completed(self):
        success, data = ReminderContainer.count_local_completed()
        assert success is True
        assert isinstance(data, int)

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud")
    def test_delete_local_completed(self):
        success, data = ReminderContainer.delete_local_completed()
        assert success is True
        success, count = ReminderContainer.count_local_completed()
        assert count == 0

    def test_assoc_list_local_remote(self):
        mock_local = [LocalList("sync_me"), LocalList("do_not_sync_me")]
        mock_remote = [RemoteCalendar(calendar_name="sync_me"), RemoteCalendar(calendar_name="do_not_sync_me")]
        mock_sync = ['sync_me']
        success, data = ReminderContainer.assoc_list_local_remote(mock_local, mock_remote, mock_sync)
        assert success is True
        assoc_containers = ReminderContainer.CONTAINER_LIST

        synced_container = [c for c in assoc_containers if c.local_list.name == "sync_me"]
        assert len(synced_container) == 1
        assert synced_container[0].sync is True

        not_synced_container = [c for c in assoc_containers if c.local_list.name == "do_not_sync_me"]
        assert len(not_synced_container) == 1
        assert not_synced_container[0].sync is False

    def test_assoc_list_remote_local(self):
        mock_local = [LocalList("sync_me"), LocalList("do_not_sync_me")]
        mock_remote = [RemoteCalendar(calendar_name="sync_me"), RemoteCalendar(calendar_name="do_not_sync_me")]
        mock_sync = ['sync_me']
        success, data = ReminderContainer.assoc_list_remote_local(mock_local, mock_remote, mock_sync)
        assert success is True
        assoc_containers = ReminderContainer.CONTAINER_LIST

        synced_container = [c for c in assoc_containers if c.local_list.name == "sync_me"]
        assert len(synced_container) == 1
        assert synced_container[0].sync is True

        not_synced_container = [c for c in assoc_containers if c.local_list.name == "do_not_sync_me"]
        assert len(not_synced_container) == 1
        assert not_synced_container[0].sync is False

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud and CalDAV credentials")
    def test_create_linked_containers(self):
        helpers.DRY_RUN = False
        TestReminderContainer.__connect_caldav()
        mock_local = [LocalList("sync_me"),
                      LocalList("do_not_sync_me"),
                      LocalList("Reminders"),
                      LocalList("local_only")]
        mock_remote = [RemoteCalendar(calendar_name="sync_me"),
                       RemoteCalendar(calendar_name="do_not_sync_me"),
                       RemoteCalendar(calendar_name="Tasks"),
                       RemoteCalendar(calendar_name="remote_only")]
        mock_sync = ['sync_me', 'Reminders', 'local_only', 'remote_only']
        success, data = ReminderContainer.create_linked_containers(mock_local, mock_remote, mock_sync)

        assert success is True
        assoc_containers = ReminderContainer.CONTAINER_LIST

        synced_container = [c for c in assoc_containers if c.local_list.name == "sync_me"]
        assert len(synced_container) == 1
        assert synced_container[0].sync is True

        not_synced_container = [c for c in assoc_containers if c.local_list.name == "do_not_sync_me"]
        assert len(not_synced_container) == 1
        assert not_synced_container[0].sync is False

        # Tests Reminders <-> Tasks association
        reminders_tasks_container = [c for c in assoc_containers if
                                     c.local_list.name == "Reminders" and c.remote_calendar.name == "Tasks"]
        assert len(reminders_tasks_container) == 1
        assert reminders_tasks_container[0].sync is True

        # Test local list gets created
        success, local_lists = ReminderContainer.load_local_lists()
        remote_only = [lst for lst in local_lists if lst.name == "remote_only"]
        assert len(remote_only) == 1

        # Test remote calendar gets created
        success, remote_calendars = ReminderContainer.load_caldav_calendars()
        local_only = [cal for cal in remote_calendars if cal.name == "local_only"]
        assert len(local_only) == 1

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires local filesystem.")
    def test_seed_container_table(self):
        ReminderContainer.seed_container_table()
        try:
            with closing(sqlite3.connect(helpers.db_folder())) as connection:
                connection.row_factory = sqlite3.Row
                with closing(connection.cursor()) as cursor:
                    sql_table_exists = "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_container';"
                    table_result = cursor.execute(sql_table_exists)

                    table_list = [t for t in table_result if t['name'] == "tb_container"]
                    assert len(table_list) == 1

                    sql_columns_exist = "PRAGMA table_info('tb_container');"
                    columns_result = cursor.execute(sql_columns_exist)

                    columns = ['id', 'local_name', 'remote_name', 'sync']
                    for col in columns_result:
                        assert col['name'] in columns
        except sqlite3.OperationalError as e:
            assert False, repr(e)

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires local filesystem.")
    def test_persist_containers(self):
        ReminderContainer(LocalList("sync_me"), RemoteCalendar(calendar_name="sync_me"), True)
        ReminderContainer(LocalList("do_not_sync_me"), RemoteCalendar(calendar_name="do_not_sync_me"), False)
        ReminderContainer.persist_containers()

        try:
            with closing(sqlite3.connect(helpers.db_folder())) as connection:
                connection.row_factory = sqlite3.Row
                with closing(connection.cursor()) as cursor:
                    sql_get_containers = "SELECT * FROM tb_container;"
                    results = cursor.execute(sql_get_containers).fetchall()

                    assert len(results) == 2
                    for result in results:
                        if result['local_name'] == 'sync_me':
                            assert result['remote_name'] == 'sync_me'
                            assert result['sync'] == 1
                        elif result['local_name'] == 'do_not_sync_me':
                            assert result['remote_name'] == 'do_not_sync_me'
                            assert result['sync'] == 0
                        else:
                            assert False, 'Unrecognised record in tb_container'
        except sqlite3.OperationalError as e:
            assert False, repr(e)

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires local filesystem.")
    def test_seed_reminder_table(self):
        ReminderContainer.seed_reminder_table()
        try:
            with closing(sqlite3.connect(helpers.db_folder())) as connection:
                connection.row_factory = sqlite3.Row
                with closing(connection.cursor()) as cursor:
                    sql_table_exists = "SELECT name FROM sqlite_master WHERE type='table' AND name='tb_reminder';"
                    table_result = cursor.execute(sql_table_exists)

                    table_list = [t for t in table_result if t['name'] == "tb_reminder"]
                    assert len(table_list) == 1

                    sql_columns_exist = "PRAGMA table_info('tb_reminder');"
                    columns_result = cursor.execute(sql_columns_exist)

                    columns = ['id', 'local_uuid', 'local_name', 'remote_uuid', 'remote_name', 'local_container',
                               'remote_container']
                    for col in columns_result:
                        assert col['name'] in columns
        except sqlite3.OperationalError as e:
            assert False, repr(e)

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires local filesystem.")
    def test_persist_reminders(self):
        container = ReminderContainer(LocalList("sync_me"), RemoteCalendar(calendar_name="sync_me"), True)
        local_reminder = Reminder("local_uuid", "local_name", None, datetime.datetime.now(),
                                  None, None, None, None, False)
        remote_reminder = Reminder("remote_uuid", "remote_name", None, datetime.datetime.now(),
                                   None, None, None, None, False)
        container.local_reminders.append(local_reminder)
        container.remote_reminders.append(remote_reminder)
        ReminderContainer.persist_reminders()

        try:
            with closing(sqlite3.connect(helpers.db_folder())) as connection:
                connection.row_factory = sqlite3.Row
                with closing(connection.cursor()) as cursor:
                    sql_get_containers = "SELECT * FROM tb_reminder;"
                    results = cursor.execute(sql_get_containers).fetchall()
                    assert len(results) >= 2

                    local_persisted = [r for r in results if r['local_name'] == 'local_name']
                    assert len(local_persisted) >= 1
                    local = local_persisted[0]
                    assert local['local_uuid'] == 'local_uuid'
                    assert local['local_container'] == 'sync_me'

                    remote_persisted = [r for r in results if r['remote_name'] == 'remote_name']
                    assert len(remote_persisted) >= 1
                    remote = remote_persisted[0]
                    assert remote['remote_uuid'] == 'remote_uuid'
                    assert remote['remote_container'] == 'sync_me'
        except sqlite3.OperationalError as e:
            assert False, repr(e)

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires CalDAV credentials")
    def test__delete_remote_containers(self):
        helpers.DRY_RUN = False
        TestReminderContainer.__connect_caldav()

        # Create a remote container
        to_delete = RemoteCalendar(calendar_name='DELETE_ME')
        to_keep = RemoteCalendar(calendar_name='KEEP_ME')
        success, data = to_delete.create()
        if not success:
            assert False, 'Could not create remote container: {}'.format(data)
        success, data = to_keep.create()
        if not success:
            assert False, 'Could not create remote container: {}'.format(data)

        # Run the function
        removed_local_containers = [{'local_name': 'DELETE_ME'}]
        discovered_remote = [to_delete, to_keep]
        to_sync = ['DELETE_ME', 'KEEP_ME']
        result = {'updated_remote_list': []}
        # noinspection PyTypeChecker
        success, data = ReminderContainer._delete_remote_containers(removed_local_containers, discovered_remote, to_sync,
                                                                    result)

        # Check that the remote container has been deleted
        assert success is True, 'Could not delete remote container: {}'.format(data)
        success, data = ReminderContainer.load_caldav_calendars()
        assert success is True, 'Could not load remote calendars: {}'.format(data)
        remote_calendars = data
        keep_list = [c for c in remote_calendars if c.name == "KEEP_ME"]
        assert len(keep_list) > 0
        delete_list = [c for c in remote_calendars if c.name == "DELETE_ME"]
        assert len(delete_list) == 0

        # Check the results are properly updated
        deleted_calendar = next((c for c in result['updated_remote_list'] if c.name == 'DELETE_ME'), None)
        assert deleted_calendar is None

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud")
    def test__delete_local_containers(self):
        helpers.DRY_RUN = False

        # Create a local container
        to_delete = LocalList('DELETE_ME')
        to_keep = LocalList('KEEP_ME')
        success, data = to_delete.create()
        if not success:
            assert False, 'Could not create local container: {}'.format(data)
        success, data = to_keep.create()
        if not success:
            assert False, 'Could not create local container: {}'.format(data)

        # Run the function
        removed_remote_containers = [{'remote_name': 'DELETE_ME'}]
        removed_local_containers = []
        discovered_local = [to_delete, to_keep]
        to_sync = ['DELETE_ME', 'KEEP_ME']
        result = {'updated_local_list': []}
        # noinspection PyTypeChecker
        success, data = ReminderContainer._delete_local_containers(removed_remote_containers, removed_local_containers,
                                                                   discovered_local, to_sync, result)

        # Check that the local container has been deleted
        assert success is True, 'Could not delete local container: {}'.format(data)
        success, data = ReminderContainer.load_local_lists()
        assert success is True, 'Could not load local lists: {}'.format(data)
        local_lists = data
        keep_list = [lst for lst in local_lists if lst.name == 'KEEP_ME']
        assert len(keep_list) > 0
        delete_list = [lst for lst in local_lists if lst.name == 'DELETE_ME']
        assert len(delete_list) == 0

        # Check the results are properly updated
        deleted_list = next((lst for lst in result['updated_local_list'] if lst.name == 'DELETE_ME'), None)
        assert deleted_list is None

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud and CalDAV credentials")
    def test_sync_container_deletions(self):
        TestReminderContainer.__connect_caldav()
        helpers.DRY_RUN = False

        # Create containers to be deleted
        delete_local = LocalList("DELETE_LOCAL")
        success, data = delete_local.create()
        if not success:
            assert False, 'Could not create local list {}'.format(delete_local.name)
        delete_remote = RemoteCalendar(calendar_name="DELETE_REMOTE")
        success, data = delete_remote.create()
        if not success:
            assert False, 'Could not create remote calendar {}'.format(delete_remote.name)

        # Fetch current containers
        success, data = ReminderContainer.load_local_lists()
        if not success:
            assert False, 'Could not load local lists {}'.format(data)
        discovered_local = data
        success, data = ReminderContainer.load_caldav_calendars()
        if not success:
            assert False, 'Could not load remote calendars {}'.format(data)
        discovered_remote = data

        # Persist containers
        to_sync = ['DELETE_LOCAL', 'DELETE_REMOTE']
        success, data = ReminderContainer.create_linked_containers(discovered_local, discovered_remote, to_sync)
        if not success:
            assert False, 'Could not create linked containers'

        # Delete the containers
        success, data = delete_local.delete()
        if not success:
            assert False, 'Could not delete local list {}'.format(delete_local.name)
        success, data = delete_remote.delete()
        if not success:
            assert False, 'Could not delete remote calendar {}'.format(delete_remote.name)

        # Fetch current containers
        success, data = ReminderContainer.load_local_lists()
        if not success:
            assert False, 'Could not load local lists {}'.format(data)
        discovered_local = data
        success, data = ReminderContainer.load_caldav_calendars()
        if not success:
            assert False, 'Could not load remote calendars {}'.format(data)
        discovered_remote = data

        # Synchronise the deletion
        ReminderContainer.sync_container_deletions(discovered_local, discovered_remote, to_sync)

        # Ensure the containers have been deleted
        success, data = ReminderContainer.load_local_lists()
        if not success:
            assert False, 'Could not load local lists {}'.format(data)
        local_lists = data
        success, data = ReminderContainer.load_caldav_calendars()
        if not success:
            assert False, 'Could not load remote calendars {}'.format(data)
        remote_calendars = data
        local_presence = next((lst for lst in local_lists if lst.name == "DELETE_LOCAL"), None)
        remote_presence = next((cal for cal in remote_calendars if cal.name == "DELETE_REMOTE"), None)
        assert local_presence is None
        assert remote_presence is None

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud and CalDAV credentials")
    def test__delete_remote_reminders(self):
        helpers.DRY_RUN = False
        TestReminderContainer.__connect_caldav()

        # Fetch containers
        success, data = ReminderContainer.load_local_lists()
        if not success:
            assert False, 'Could not load local lists {}'.format(data)
        discovered_local = data
        success, data = ReminderContainer.load_caldav_calendars()
        if not success:
            assert False, 'Could not load remote calendars {}'.format(data)
        discovered_remote = data

        # Associate containers and find the Sync container
        ReminderContainer.create_linked_containers(discovered_local, discovered_remote, ['Sync'])
        sync_container = next((c for c in ReminderContainer.CONTAINER_LIST if c.local_list.name == "Sync"))

        # Create the reminder which will be deleted
        to_delete = Reminder(None, "DELETE_ME", None, datetime.datetime.now(), None,
                             None, None, None)
        success, data = to_delete.upsert_local(sync_container)
        if not success:
            assert False, 'Failed to create local reminder.'
        to_delete.uuid = data
        success, data = to_delete.upsert_remote(sync_container)
        if not success:
            assert False, 'Failed to create remote task.'

        # Refresh the container with the new reminder, and persist
        sync_container.load_local_reminders()
        sync_container.load_remote_reminders()
        sync_container.persist_reminders()

        # Delete the reminder locally
        delete_reminder_script = reminderscript.delete_reminder_script
        return_code, stdout, stderr = helpers.run_applescript(delete_reminder_script, to_delete.uuid)
        if return_code != 0:
            assert False, 'Failed to delete local reminder: {}'.format(stderr)

        # Refresh the container
        sync_container.local_reminders.clear()
        sync_container.load_local_reminders()
        sync_container.load_remote_reminders()

        # Get persisted reminders
        success, data = ReminderContainer.get_saved_reminders()
        if not success:
            assert False, 'Could not get saved reminders: {}'.format(data)
        saved_reminders = data
        container_saved_local = [r for r in saved_reminders if r['local_container'] == sync_container.local_list.name]

        # Synchronise the deletion
        result = {'deleted_remote_reminders': []}
        success, data = ReminderContainer._delete_remote_reminders(container_saved_local, sync_container, result)
        if not success:
            assert False, 'Failed to delete remote reminder: {}'.format(data)

        # Ensure the locally deleted reminder has been deleted remotely
        deleted_reminder = next((dr for dr in result['deleted_remote_reminders'] if dr.name == to_delete.name), None)
        assert deleted_reminder is not None

    @pytest.mark.skipif(TEST_ENV != 'local', reason="Requires Mac system with iCloud and CalDAV credentials")
    def test__delete_local_reminders(self):
        helpers.DRY_RUN = False
        TestReminderContainer.__connect_caldav()

        # Fetch containers
        success, data = ReminderContainer.load_local_lists()
        if not success:
            assert False, 'Could not load local lists {}'.format(data)
        discovered_local = data
        success, data = ReminderContainer.load_caldav_calendars()
        if not success:
            assert False, 'Could not load remote calendars {}'.format(data)
        discovered_remote = data

        # Associate containers and find the Sync container
        ReminderContainer.create_linked_containers(discovered_local, discovered_remote, ['Sync'])
        sync_container = next((c for c in ReminderContainer.CONTAINER_LIST if c.local_list.name == "Sync"))

        # Create the reminder which will be deleted
        to_delete = Reminder(None, "DELETE_ME", None, datetime.datetime.now(), None,
                             None, None, None)
        success, data = to_delete.upsert_local(sync_container)
        if not success:
            assert False, 'Failed to create local reminder.'
        to_delete.uuid = data
        success, data = to_delete.upsert_remote(sync_container)
        if not success:
            assert False, 'Failed to create remote task.'

        # Refresh the container with the new reminder, and persist
        sync_container.load_local_reminders()
        sync_container.load_remote_reminders()
        sync_container.persist_reminders()

        # Delete the reminder remotely
        to_delete_remote = sync_container.remote_calendar.cal_obj.search(todo=True, uid=to_delete.uuid)
        remote_reminder = next((r for r in sync_container.remote_reminders
                                if r.uuid == to_delete.uuid or r.name == to_delete.name), None)
        if len(to_delete_remote) > 0:
            to_delete_remote[0].delete()
            sync_container.remote_reminders.remove(remote_reminder)

        # Refresh the container
        sync_container.remote_reminders.clear()
        sync_container.load_local_reminders()
        sync_container.load_remote_reminders()

        # Get persisted reminders
        success, data = ReminderContainer.get_saved_reminders()
        if not success:
            assert False, 'Could not get saved reminders: {}'.format(data)
        saved_reminders = data
        container_saved_remote = [r for r in saved_reminders if r['remote_container'] == sync_container.remote_calendar.name]

        # Synchronise the deletion
        result = {'deleted_local_reminders': []}
        success, data = ReminderContainer._delete_local_reminders(container_saved_remote, sync_container, result)
        if not success:
            assert False, 'Failed to delete local reminder: {}'.format(data)

        # Ensure the remotely deleted reminder has been deleted locally
        deleted_reminder = next((dr for dr in result['deleted_local_reminders'] if dr.name == to_delete.name), None)
        assert deleted_reminder is not None

    def test_get_saved_reminders(self):
        assert False

    def test_sync_reminder_deletions(self):
        assert False

    def test_load_local_reminders(self):
        assert False

    def test_load_remote_reminders(self):
        assert False

    def test_sync_local_reminders_to_remote(self):
        assert False

    def test_sync_remote_reminders_to_local(self):
        assert False

    def test_sync_reminders(self):
        assert False
