import tempfile
import unittest
import json
from pathlib import Path
import app
import owner_builder as builder


class FormattingTests(unittest.TestCase):
    def test_base_structure_version_migrates_legacy_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'legacy.sqlite3'
            app.initialise_database_at(path)
            state=builder.config(path)
            legacy=dict(state['draft'])
            legacy.pop('base_structure', None)
            with builder.connect(path) as c:
                c.execute('UPDATE builder_config SET draft=?, published=? WHERE id=1',
                          (json.dumps(legacy), json.dumps(legacy)))
            migrated=builder.config(path)
            self.assertEqual(migrated['draft']['base_structure']['version'], builder.BASE_STRUCTURE_VERSION)
            self.assertEqual(migrated['draft']['base_structure']['navigation'], migrated['draft']['navigation'])
            self.assertEqual(migrated['draft']['base_structure']['weather']['refresh_minutes'], 15)

    def test_builder_ux_affordances_are_present(self):
        source=(Path(__file__).parent/'static'/'owner-builder.js').read_text(encoding='utf-8')
        for marker in ('data-reset-travel', 'data-reset-base', 'base-structure', 'beforeunload', 'data-travel-prop'):
            self.assertIn(marker, source)
        for page in ('static/owner-builder.html',):
            html=(Path(__file__).parent / page).read_text(encoding='utf-8')
            self.assertIn('Core experience', html)
            self.assertIn('Data & journeys', html)

    def test_add_shifts_supports_arbitrary_date_picker(self):
        source=(Path(__file__).parent/'static'/'week-planner.js').read_text(encoding='utf-8')
        self.assertIn('data-week-date', source)
        self.assertIn('Choose any date', source)
        self.assertIn('monday(fromIso(el.value))', source)

    def test_travel_results_defaults_and_persistence(self):
        defaults=builder.travel_results_validate({})
        self.assertTrue(defaults['show_best_only'])
        self.assertTrue(defaults['show_more'])
        self.assertTrue(defaults['visibility']['leave_by'])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite3'
            app.initialise_database_at(path)
            state=builder.config(path)
            doc=state['draft']
            doc['travel_results']['show_best_only']=False
            doc['travel_results']['visibility']['traffic_adjustment']=False
            saved=builder.save_config(path,{'revision':state['revision'],'document':doc})
            self.assertFalse(saved['draft']['travel_results']['show_best_only'])
            self.assertFalse(saved['draft']['travel_results']['visibility']['traffic_adjustment'])

    def test_defaults_and_invalid_values(self):
        self.assertEqual(builder.formatting_validate({})['columns'], '1')
        for value in ({'accent':'red;display:none'}, {'columns':'9'}, {'size':200}, {'font':'url(x)'}, None):
            with self.assertRaises(builder.BuilderError):
                builder.formatting_validate(value)

    def test_save_publish_and_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite3'
            app.initialise_database_at(path)
            state=builder.config(path)
            doc=state['draft']
            doc['formatting']={'accent':'#123456','columns':'2','font':'serif','size':'18'}
            saved=builder.save_config(path,{'revision':state['revision'],'document':doc})
            self.assertEqual(saved['draft']['formatting']['columns'],'2')
            self.assertNotEqual(saved['published'].get('formatting',{}).get('accent'),'#123456')
            published=builder.save_config(path,{'revision':saved['revision'],'document':saved['draft']},publish=True)
            self.assertEqual(published['published']['formatting']['accent'],'#123456')
            self.assertEqual(builder.config(path)['published']['formatting']['font'],'serif')
