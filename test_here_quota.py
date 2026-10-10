import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
import here_quota as quota
import here_transit as transit
from datetime import datetime, timezone


def test_quota_failure_never_calls_here():
    with patch.dict(os.environ, {'ALIGN_HERE_TRANSIT_ENABLED': '1', 'ALIGN_HERE_ROUTING_KEY': 'test'}), patch.object(quota, 'reserve', side_effect=ValueError('Limit reached')), patch.object(transit, 'request_json') as request:
        with pytest.raises(ValueError, match='Limit reached'):
            transit.HERETransitProvider().plan((53, -3), (53, -2), datetime.now(timezone.utc), ['bus'])
        request.assert_not_called()


def test_quota_requires_durable_store():
    with patch.object(quota, 'postgres_enabled', return_value=False):
        with pytest.raises(ValueError, match='persistent'):
            quota.reserve()


def test_hosted_driving_and_geocoding_reserve_before_request():
    import personal_planner
    with patch('sqlite_support.postgres_enabled', return_value=True), patch.object(quota, 'reserve', side_effect=ValueError('Limit reached')), patch.object(personal_planner, 'fetch_json') as request:
        with pytest.raises(ValueError, match='Limit reached'):
            personal_planner.here_point('test', 'Liverpool')
        request.assert_not_called()


def test_shared_quota_survives_connections_and_concurrency():
    dsn = os.environ.get('ALIGN_TEST_POSTGRES_URL')
    if not dsn:
        pytest.skip('Requires isolated test PostgreSQL')
    import psycopg
    from psycopg import sql
    import postgres_support
    schema = 'test_here_' + uuid.uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    try:
        with patch.dict(os.environ, {'DATABASE_URL': dsn, 'ALIGN_DATABASE_BACKEND': 'postgres'}), patch.object(postgres_support, 'schema_for', return_value=schema), patch.object(quota, 'LIMIT', 3):
            def attempt(_):
                try:
                    quota.reserve()
                    return True
                except ValueError:
                    return False
            with ThreadPoolExecutor(max_workers=6) as pool:
                assert sum(pool.map(attempt, range(8))) == 3
            # A fresh connection cannot reset a consumed allowance.
            assert not attempt(None)
    finally:
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
