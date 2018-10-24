import os
import copy
import pytest
import re
from unittest.mock import Mock

import numpy as np
import pandas as pd
from numpy import testing as npt

from pyam import (IamDataFrame, OpenSCMDataFrame, plotting, validate, categorize,
                  require_variable, check_aggregate, filter_by_meta, META_IDX,
                  IAMC_IDX)
from pyam.core import _meta_idx
from pyam.errors import ConversionError

from conftest import TEST_DATA_DIR


df_filter_by_meta_matching_idx = pd.DataFrame([
    ['a_model', 'a_scenario', 'a_region1', 1],
    ['a_model', 'a_scenario', 'a_region2', 2],
    ['a_model', 'a_scenario2', 'a_region3', 3],
], columns=['model', 'scenario', 'region', 'col'])


df_filter_by_meta_nonmatching_idx = pd.DataFrame([
    ['a_model', 'a_scenario3', 'a_region1', 1, 2],
    ['a_model', 'a_scenario3', 'a_region2', 2, 3],
    ['a_model', 'a_scenario2', 'a_region3', 3, 4],
], columns=['model', 'scenario', 'region', 2010, 2020]
).set_index(['model', 'region'])


def test_init_df_with_index(test_pd_df):
    df = IamDataFrame(test_pd_df.set_index(META_IDX))
    pd.testing.assert_frame_equal(df.timeseries().reset_index(), test_pd_df)


def test_init_df_with_float_cols_raises(test_pd_df):
    _test_df_iam = test_pd_df.rename(columns={2005: 2005.5, 2010: 2010.})
    pytest.raises(ValueError, IamDataFrame, data=_test_df_iam)


def test_init_df_with_float_cols(test_pd_df):
    _test_df_iam = test_pd_df.rename(columns={2005: 2005., 2010: 2010.})
    obs = IamDataFrame(_test_df_iam).timeseries().reset_index()
    pd.testing.assert_series_equal(obs[2005], test_pd_df[2005])


def test_init_df_from_timeseries(test_df_iam):
    df = IamDataFrame(test_df_iam.timeseries())
    pd.testing.assert_frame_equal(df.timeseries(), test_df_iam.timeseries())


def test_get_item_iam(test_df):
    assert test_df['model'].unique() == ['a_model']


def test_model(test_df):
    pd.testing.assert_series_equal(test_df.models(),
                                   pd.Series(data=['a_model'], name='model'))


def test_scenario(test_df):
    exp = pd.Series(data=['a_scenario'], name='scenario')
    pd.testing.assert_series_equal(test_df.scenarios(), exp)


def test_region(test_df):
    exp = pd.Series(data=['World'], name='region')
    pd.testing.assert_series_equal(test_df.regions(), exp)


def test_variable(test_df):
    exp = pd.Series(
        data=['Primary Energy', 'Primary Energy|Coal'], name='variable')
    pd.testing.assert_series_equal(test_df.variables(), exp)


def test_variable_unit(test_df):
    dct = {'variable': ['Primary Energy', 'Primary Energy|Coal'],
           'unit': ['EJ/y', 'EJ/y']}
    exp = pd.DataFrame.from_dict(dct)[['variable', 'unit']]
    npt.assert_array_equal(test_df.variables(include_units=True), exp)


def test_variable_depth_0(test_df):
    obs = list(test_df.filter(level=0)['variable'].unique())
    exp = ['Primary Energy']
    assert obs == exp


def test_variable_depth_0_keep_false(test_df):
    obs = list(test_df.filter(level=0, keep=False)['variable'].unique())
    exp = ['Primary Energy|Coal']
    assert obs == exp


def test_variable_depth_0_minus(test_df):
    obs = list(test_df.filter(level='0-')['variable'].unique())
    exp = ['Primary Energy']
    assert obs == exp


def test_variable_depth_0_plus(test_df):
    obs = list(test_df.filter(level='0+')['variable'].unique())
    exp = ['Primary Energy', 'Primary Energy|Coal']
    assert obs == exp


def test_variable_depth_1(test_df):
    obs = list(test_df.filter(level=1)['variable'].unique())
    exp = ['Primary Energy|Coal']
    assert obs == exp


def test_variable_depth_1_minus(test_df):
    obs = list(test_df.filter(level='1-')['variable'].unique())
    exp = ['Primary Energy', 'Primary Energy|Coal']
    assert obs == exp


def test_variable_depth_1_plus(test_df):
    obs = list(test_df.filter(level='1+')['variable'].unique())
    exp = ['Primary Energy|Coal']
    assert obs == exp


def test_variable_depth_raises(test_df):
    pytest.raises(ValueError, test_df.filter, level='1/')


def test_filter_error(test_df):
    pytest.raises(ValueError, test_df.filter, foo='foo')


def test_filter_as_kwarg(meta_df_iam):
    obs = list(meta_df_iam.filter(variable='Primary Energy|Coal').scenarios())
    assert obs == ['a_scenario']


def test_filter_keep_false(meta_df_iam):
    df = meta_df_iam.filter(variable='Primary Energy|Coal', year=2005, keep=False)
    obs = df.data[df.data.scenario == 'a_scenario'].value
    npt.assert_array_equal(obs, [1, 6, 3])


def test_filter_by_regexp(meta_df_iam):
    obs = meta_df_iam.filter(scenario='a_scenari.$', regexp=True)
    assert obs['scenario'].unique() == 'a_scenario'


def test_timeseries(test_df_iam):
    dct = {'model': ['a_model'] * 2, 'scenario': ['a_scenario'] * 2,
           'years': [2005, 2010], 'value': [1, 6]}
    exp = pd.DataFrame(dct).pivot_table(index=['model', 'scenario'],
                                        columns=['years'], values='value')
    obs = test_df_iam.filter(variable='Primary Energy').timeseries()
    npt.assert_array_equal(obs, exp)


def test_read_pandas():
    df = IamDataFrame(os.path.join(TEST_DATA_DIR, 'testing_data_2.csv'))
    assert list(df.variables()) == ['Primary Energy']


def test_filter_meta_index(meta_df_iam):
    obs = meta_df_iam.filter(scenario='a_scenario2').meta.index
    exp = pd.MultiIndex(levels=[['a_model'], ['a_scenario2']],
                        labels=[[0], [0]],
                        names=['model', 'scenario'])
    pd.testing.assert_index_equal(obs, exp)


def test_meta_idx(meta_df_iam):
    # assert that the `drop_duplicates()` in `_meta_idx()` returns right length
    assert len(_meta_idx(meta_df_iam.data)) == 2


def test_require_variable(meta_df_iam):
    obs = meta_df_iam.require_variable(variable='Primary Energy|Coal',
                                   exclude_on_fail=True)
    assert len(obs) == 1
    assert obs.loc[0, 'scenario'] == 'a_scenario2'

    assert list(meta_df_iam['exclude']) == [False, True]


def test_require_variable_top_level(meta_df_iam):
    obs = require_variable(meta_df_iam, variable='Primary Energy|Coal',
                           exclude_on_fail=True)
    assert len(obs) == 1
    assert obs.loc[0, 'scenario'] == 'a_scenario2'

    assert list(meta_df_iam['exclude']) == [False, True]


def test_validate_all_pass(meta_df_iam):
    obs = meta_df_iam.validate(
        {'Primary Energy': {'up': 10}}, exclude_on_fail=True)
    assert obs is None
    assert len(meta_df_iam.data) == 6  # data unchanged

    assert list(meta_df_iam['exclude']) == [False, False]  # none excluded


def test_validate_nonexisting(meta_df_iam):
    obs = meta_df_iam.validate({'Primary Energy|Coal': {'up': 2}},
                           exclude_on_fail=True)
    assert len(obs) == 1
    assert obs['scenario'].values[0] == 'a_scenario'

    assert list(meta_df_iam['exclude']) == [True, False]  # scenario with failed
    # validation excluded, scenario with non-defined value passes validation


def test_validate_up(meta_df_iam):
    obs = meta_df_iam.validate({'Primary Energy': {'up': 6.5}},
                           exclude_on_fail=False)
    assert len(obs) == 1
    assert obs['year'].values[0] == 2010

    assert list(meta_df_iam['exclude']) == [False, False]  # assert none excluded


def test_validate_lo(meta_df_iam):
    obs = meta_df_iam.validate({'Primary Energy': {'up': 8, 'lo': 2.0}})
    assert len(obs) == 1
    assert obs['year'].values[0] == 2005
    assert list(obs['scenario'].values) == ['a_scenario']


def test_validate_both(meta_df_iam):
    obs = meta_df_iam.validate({'Primary Energy': {'up': 6.5, 'lo': 2.0}})
    assert len(obs) == 2
    assert list(obs['year'].values) == [2005, 2010]
    assert list(obs['scenario'].values) == ['a_scenario', 'a_scenario2']


def test_validate_year(meta_df_iam):
    obs = meta_df_iam.validate({'Primary Energy': {'up': 5.0, 'year': 2005}},
                           exclude_on_fail=False)
    assert obs is None

    obs = meta_df_iam.validate({'Primary Energy': {'up': 5.0, 'year': 2010}},
                           exclude_on_fail=False)
    assert len(obs) == 2


def test_validate_exclude(meta_df_iam):
    meta_df_iam.validate({'Primary Energy': {'up': 6.0}}, exclude_on_fail=True)
    assert list(meta_df_iam['exclude']) == [False, True]


def test_validate_top_level(meta_df_iam):
    obs = validate(meta_df_iam, criteria={'Primary Energy': {'up': 6.0}},
                   exclude_on_fail=True, variable='Primary Energy')
    assert len(obs) == 1
    assert obs['year'].values[0] == 2010
    assert list(meta_df_iam['exclude']) == [False, True]


def test_check_aggregate_pass(check_aggregate_df_iam):
    obs = check_aggregate_df_iam.filter(
        scenario='a_scenario'
    ).check_aggregate('Primary Energy')
    assert obs is None


def test_check_aggregate_fail(meta_df_iam):
    obs = meta_df_iam.check_aggregate('Primary Energy', exclude_on_fail=True)
    assert len(obs.columns) == 2
    assert obs.index.get_values()[0] == (
        'Primary Energy', 'a_model', 'a_scenario', 'World'
    )


def test_check_aggregate_top_level(meta_df_iam):
    obs = check_aggregate(meta_df_iam, variable='Primary Energy', year=2005)
    assert len(obs.columns) == 1
    assert obs.index.get_values()[0] == (
        'Primary Energy', 'a_model', 'a_scenario', 'World'
    )


def test_df_iam_check_aggregate_pass(check_aggregate_df_iam):
    obs = check_aggregate_df_iam.check_aggregate('Primary Energy')
    assert obs is None

    for variable in check_aggregate_df_iam.variables():
        obs = check_aggregate_df_iam.check_aggregate(variable)
        assert obs is None


def test_df_iam_check_aggregate_regions_pass(check_aggregate_df_iam):
    obs = check_aggregate_df_iam.check_aggregate_regions('Primary Energy')
    assert obs is None

    for variable in check_aggregate_df_iam.variables():
        obs = check_aggregate_df_iam.check_aggregate_regions(variable)
        assert obs is None


def run_check_agg_fail(pyam_df, tweak_dict, test_type):
    mr = pyam_df.data.model == tweak_dict['model']
    sr = pyam_df.data.scenario == tweak_dict['scenario']
    rr = pyam_df.data.region == tweak_dict['region']
    vr = pyam_df.data.variable == tweak_dict['variable']
    ur = pyam_df.data.unit == tweak_dict['unit']

    row_to_tweak = mr & sr & rr & vr & ur
    assert row_to_tweak.any()

    pyam_df.data.value.iloc[np.where(row_to_tweak)[0]] *= 0.99

    # the error variable is always the top level one
    expected_index = tweak_dict
    agg_test = test_type == 'aggregate'
    region_world_only_contrib = test_type == 'region-world-only-contrib'
    if agg_test or region_world_only_contrib:
        expected_index['variable'] = '|'.join(
            expected_index['variable'].split('|')[:2]
        )
    elif 'region' in test_type:
        expected_index['region'] = 'World'

    # units get dropped during aggregation and the index is a list
    expected_index = [v for k, v in expected_index.items() if k != 'unit']

    for variable in pyam_df.variables():
        if test_type == 'aggregate':
            obs = pyam_df.check_aggregate(
                variable,
            )
        elif 'region' in test_type:
            obs = pyam_df.check_aggregate_regions(
                variable,
            )

        if obs is not None:
            assert len(obs.columns) == 2
            assert set(obs.index.get_values()[0]) == set(expected_index)


def test_df_iam_check_aggregate_fail(check_aggregate_df_iam):
    to_tweak = {
        'model': 'IMG',
        'scenario': 'a_scen_2',
        'region': 'R5REF',
        'variable': 'Emissions|CO2',
        'unit': 'Mt CO2/yr',
    }
    run_check_agg_fail(check_aggregate_df_iam, to_tweak, 'aggregate')


def test_df_iam_check_aggregate_fail_no_regions(check_aggregate_df_iam):
    to_tweak = {
        'model': 'MSG-GLB',
        'scenario': 'a_scen_2',
        'region': 'World',
        'variable': 'Emissions|C2F6|Solvents',
        'unit': 'kt C2F6/yr',
    }
    run_check_agg_fail(check_aggregate_df_iam, to_tweak, 'aggregate')


def test_df_iam_check_aggregate_region_fail(check_aggregate_df_iam):
    to_tweak = {
        'model': 'IMG',
        'scenario': 'a_scen_2',
        'region': 'World',
        'variable': 'Emissions|CO2',
        'unit': 'Mt CO2/yr',
    }

    run_check_agg_fail(check_aggregate_df_iam, to_tweak, 'region')


def test_df_iam_check_aggregate_region_fail_no_subsector(check_aggregate_df_iam):
    to_tweak = {
        'model': 'MSG-GLB',
        'scenario': 'a_scen_2',
        'region': 'R5REF',
        'variable': 'Emissions|CH4',
        'unit': 'Mt CH4/yr',
    }

    run_check_agg_fail(check_aggregate_df_iam, to_tweak, 'region')


def test_df_iam_check_aggregate_region_fail_world_only_var(check_aggregate_df_iam):
    to_tweak = {
        'model': 'MSG-GLB',
        'scenario': 'a_scen_2',
        'region': 'World',
        'variable': 'Emissions|CO2|Agg Agg',
        'unit': 'Mt CO2/yr',
    }

    run_check_agg_fail(
        check_aggregate_df_iam, to_tweak, 'region-world-only-contrib'
    )


def test_df_iam_check_aggregate_regions_errors(check_aggregate_regional_df_iam):
    # these tests should fail because our dataframe has continents and regions
    # so checking without providing components leads to double counting and
    # hence failure
    obs = check_aggregate_regional_df_iam.check_aggregate_regions(
        'Emissions|N2O', 'World'
    )

    assert len(obs.columns) == 2
    assert obs.index.get_values()[0] == (
        'World', 'AIM', 'cscen', 'Emissions|N2O'
    )

    obs = check_aggregate_regional_df_iam.check_aggregate_regions(
        'Emissions|N2O', 'REUROPE'
    )

    assert len(obs.columns) == 2
    assert obs.index.get_values()[0] == (
        'REUROPE', 'AIM', 'cscen', 'Emissions|N2O'
    )


def test_df_iam_check_aggregate_regions_components(check_aggregate_regional_df_iam):
    obs = check_aggregate_regional_df_iam.check_aggregate_regions(
        'Emissions|N2O', 'World', components=['REUROPE', 'RASIA']
    )
    assert obs is None

    obs = check_aggregate_regional_df_iam.check_aggregate_regions(
        'Emissions|N2O|Solvents', 'World', components=['REUROPE', 'RASIA']
    )
    assert obs is None

    obs = check_aggregate_regional_df_iam.check_aggregate_regions(
        'Emissions|N2O', 'REUROPE', components=['Germany', 'UK']
    )
    assert obs is None

    obs = check_aggregate_regional_df_iam.check_aggregate_regions(
        'Emissions|N2O|Transport', 'REUROPE', components=['Germany', 'UK']
    )
    assert obs is None


def test_category_none(meta_df_iam):
    meta_df_iam.categorize('category', 'Testing', {'Primary Energy': {'up': 0.8}})
    assert 'category' not in meta_df_iam.meta.columns


def test_category_pass(meta_df_iam):
    dct = {'model': ['a_model', 'a_model'],
           'scenario': ['a_scenario', 'a_scenario2'],
           'category': ['foo', None]}
    exp = pd.DataFrame(dct).set_index(['model', 'scenario'])['category']

    meta_df_iam.categorize('category', 'foo', {'Primary Energy':
                                           {'up': 6, 'year': 2010}})
    obs = meta_df_iam['category']
    pd.testing.assert_series_equal(obs, exp)


def test_category_top_level(meta_df_iam):
    dct = {'model': ['a_model', 'a_model'],
           'scenario': ['a_scenario', 'a_scenario2'],
           'category': ['Testing', None]}
    exp = pd.DataFrame(dct).set_index(['model', 'scenario'])['category']

    categorize(meta_df_iam, 'category', 'Testing',
               criteria={'Primary Energy': {'up': 6, 'year': 2010}},
               variable='Primary Energy')
    obs = meta_df_iam['category']
    pd.testing.assert_series_equal(obs, exp)


def test_load_metadata(meta_df_iam):
    meta_df_iam.load_metadata(os.path.join(
        TEST_DATA_DIR, 'testing_metadata.xlsx'), sheet_name='meta')
    obs = meta_df_iam.meta

    dct = {'model': ['a_model'] * 2, 'scenario': ['a_scenario', 'a_scenario2'],
           'category': ['imported', np.nan], 'exclude': [False, False]}
    exp = pd.DataFrame(dct).set_index(['model', 'scenario'])
    pd.testing.assert_series_equal(obs['exclude'], exp['exclude'])
    pd.testing.assert_series_equal(obs['category'], exp['category'])


def test_load_SSP_database_downloaded_file(test_df_iam):
    obs_df = IamDataFrame(os.path.join(
        TEST_DATA_DIR, 'test_SSP_database_raw_download.xlsx')
    )
    pd.testing.assert_frame_equal(obs_df.as_pandas(), test_df_iam.as_pandas())


def test_load_RCP_database_downloaded_file(test_df_iam):
    obs_df = IamDataFrame(os.path.join(
        TEST_DATA_DIR, 'test_RCP_database_raw_download.xlsx')
    )
    pd.testing.assert_frame_equal(obs_df.as_pandas(), test_df_iam.as_pandas())


def test_append(test_df_iam):
    df2 = test_df_iam.append(other=os.path.join(
        TEST_DATA_DIR, 'testing_data_2.csv'))

    # check that the new meta.index is updated, but not the original one
    obs = test_df_iam.meta.index.get_level_values(1)
    npt.assert_array_equal(obs, ['a_scenario'])

    exp = ['a_scenario', 'append_scenario']
    obs2 = df2.meta.index.get_level_values(1)
    npt.assert_array_equal(obs2, exp)


def test_append_duplicates(test_df_iam):
    other = copy.deepcopy(test_df_iam)
    pytest.raises(ValueError, test_df_iam.append, other=other)


def test_interpolate(test_df_iam):
    test_df_iam.interpolate(2007)
    dct = {'model': ['a_model'] * 3, 'scenario': ['a_scenario'] * 3,
           'years': [2005, 2007, 2010], 'value': [1, 3, 6]}
    exp = pd.DataFrame(dct).pivot_table(index=['model', 'scenario'],
                                        columns=['years'], values='value')
    variable = {'variable': 'Primary Energy'}
    obs = test_df_iam.filter(**variable).timeseries()
    npt.assert_array_equal(obs, exp)

    # redo the inpolation and check that no duplicates are added
    test_df_iam.interpolate(2007)
    assert not test_df_iam.filter(**variable).data.duplicated().any()


def test_set_meta_no_name(meta_df_iam):
    idx = pd.MultiIndex(levels=[['a_scenario'], ['a_model'], ['a_region']],
                        labels=[[0], [0], [0]],
                        names=['scenario', 'model', 'region'])
    s = pd.Series(data=[0.3], index=idx)
    pytest.raises(ValueError, meta_df_iam.set_meta, s)


def test_set_meta_as_named_series(meta_df_iam):
    idx = pd.MultiIndex(levels=[['a_scenario'], ['a_model'], ['a_region']],
                        labels=[[0], [0], [0]],
                        names=['scenario', 'model', 'region'])

    s = pd.Series(data=[0.3], index=idx)
    s.name = 'meta_values'
    meta_df_iam.set_meta(s)

    idx = pd.MultiIndex(levels=[['a_model'], ['a_scenario', 'a_scenario2']],
                        labels=[[0, 0], [0, 1]], names=['model', 'scenario'])
    exp = pd.Series(data=[0.3, np.nan], index=idx)
    exp.name = 'meta_values'

    obs = meta_df_iam['meta_values']
    pd.testing.assert_series_equal(obs, exp)


def test_set_meta_as_unnamed_series(meta_df_iam):
    idx = pd.MultiIndex(levels=[['a_scenario'], ['a_model'], ['a_region']],
                        labels=[[0], [0], [0]],
                        names=['scenario', 'model', 'region'])

    s = pd.Series(data=[0.3], index=idx)
    meta_df_iam.set_meta(s, name='meta_values')

    idx = pd.MultiIndex(levels=[['a_model'], ['a_scenario', 'a_scenario2']],
                        labels=[[0, 0], [0, 1]], names=['model', 'scenario'])
    exp = pd.Series(data=[0.3, np.nan], index=idx)
    exp.name = 'meta_values'

    obs = meta_df_iam['meta_values']
    pd.testing.assert_series_equal(obs, exp)


def test_set_meta_non_unique_index_fail(meta_df_iam):
    idx = pd.MultiIndex(levels=[['a_model'], ['a_scenario'], ['a', 'b']],
                        labels=[[0, 0], [0, 0], [0, 1]],
                        names=['model', 'scenario', 'region'])
    s = pd.Series([0.4, 0.5], idx)
    pytest.raises(ValueError, meta_df_iam.set_meta, s)


def test_set_meta_non_existing_index_fail(meta_df_iam):
    idx = pd.MultiIndex(levels=[['a_model', 'fail_model'],
                                ['a_scenario', 'fail_scenario']],
                        labels=[[0, 1], [0, 1]], names=['model', 'scenario'])
    s = pd.Series([0.4, 0.5], idx)
    pytest.raises(ValueError, meta_df_iam.set_meta, s)


def test_set_meta_by_df(meta_df_iam):
    df = pd.DataFrame([
        ['a_model', 'a_scenario', 'a_region1', 1],
    ], columns=['model', 'scenario', 'region', 'col'])

    meta_df_iam.set_meta(meta=0.3, name='meta_values', index=df)

    idx = pd.MultiIndex(levels=[['a_model'], ['a_scenario', 'a_scenario2']],
                        labels=[[0, 0], [0, 1]], names=['model', 'scenario'])
    exp = pd.Series(data=[0.3, np.nan], index=idx)
    exp.name = 'meta_values'

    obs = meta_df_iam['meta_values']
    pd.testing.assert_series_equal(obs, exp)


def test_set_meta_as_series(meta_df_iam):
    s = pd.Series([0.3, 0.4])
    meta_df_iam.set_meta(s, 'meta_series')

    idx = pd.MultiIndex(levels=[['a_model'],
                                ['a_scenario', 'a_scenario2']],
                        labels=[[0, 0], [0, 1]], names=['model', 'scenario'])

    exp = pd.Series(data=[0.3, 0.4], index=idx)
    exp.name = 'meta_series'

    obs = meta_df_iam['meta_series']
    pd.testing.assert_series_equal(obs, exp)


def test_set_meta_as_int(meta_df_iam):
    meta_df_iam.set_meta(3.2, 'meta_int')

    idx = pd.MultiIndex(levels=[['a_model'],
                                ['a_scenario', 'a_scenario2']],
                        labels=[[0, 0], [0, 1]], names=['model', 'scenario'])

    exp = pd.Series(data=[3.2, 3.2], index=idx, name='meta_int')

    obs = meta_df_iam['meta_int']
    pd.testing.assert_series_equal(obs, exp)


def test_set_meta_as_str(meta_df_iam):
    meta_df_iam.set_meta('testing', name='meta_str')

    idx = pd.MultiIndex(levels=[['a_model'],
                                ['a_scenario', 'a_scenario2']],
                        labels=[[0, 0], [0, 1]], names=['model', 'scenario'])

    exp = pd.Series(data=['testing', 'testing'], index=idx, name='meta_str')

    obs = meta_df_iam['meta_str']
    pd.testing.assert_series_equal(obs, exp)


def test_set_meta_as_str_list(meta_df_iam):
    meta_df_iam.set_meta(['testing', 'testing2'], name='category')
    obs = meta_df_iam.filter(category='testing')
    assert obs['scenario'].unique() == 'a_scenario'


def test_set_meta_as_str_by_index(meta_df_iam):
    idx = pd.MultiIndex(levels=[['a_model'], ['a_scenario']],
                        labels=[[0], [0]], names=['model', 'scenario'])

    meta_df_iam.set_meta('foo', 'meta_str', idx)

    obs = pd.Series(meta_df_iam['meta_str'].values)
    pd.testing.assert_series_equal(obs, pd.Series(['foo', None]))


def test_filter_by_bool(meta_df_iam):
    meta_df_iam.set_meta([True, False], name='exclude')
    obs = meta_df_iam.filter(exclude=True)
    assert obs['scenario'].unique() == 'a_scenario'


def test_filter_by_int(meta_df_iam):
    meta_df_iam.set_meta([1, 2], name='value')
    obs = meta_df_iam.filter(value=[1, 3])
    assert obs['scenario'].unique() == 'a_scenario'


def _r5_regions_exp(df):
    df = df.filter(region='World', keep=False)
    df['region'] = 'R5MAF'
    return df.data.reset_index(drop=True)


def test_map_regions_r5(reg_df_iam):
    obs = reg_df_iam.map_regions('r5_region').data
    exp = _r5_regions_exp(reg_df_iam)
    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_map_regions_r5_region_col(reg_df_iam):
    df = reg_df_iam.filter(model='MESSAGE-GLOBIOM')
    obs = df.map_regions(
        'r5_region', region_col='MESSAGE-GLOBIOM.REGION').data
    exp = _r5_regions_exp(df)
    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_map_regions_r5_inplace(reg_df_iam):
    exp = _r5_regions_exp(reg_df_iam)
    reg_df_iam.map_regions('r5_region', inplace=True)
    obs = reg_df_iam.data
    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_map_regions_r5_agg(reg_df_iam):
    columns = reg_df_iam.data.columns
    obs = reg_df_iam.map_regions('r5_region', agg='sum').data

    exp = _r5_regions_exp(reg_df_iam)
    grp = list(columns)
    grp.remove('value')
    exp = exp.groupby(grp).sum().reset_index()
    exp = exp[columns]
    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_48a():
    # tests fix for #48 mapping many->few
    df = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'SSD', 'var', 'unit', 1, 6],
        ['model', 'scen', 'SDN', 'var', 'unit', 2, 7],
        ['model', 'scen1', 'SSD', 'var', 'unit', 2, 7],
        ['model', 'scen1', 'SDN', 'var', 'unit', 2, 7],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    ))

    exp = _r5_regions_exp(df)
    columns = df.data.columns
    grp = list(columns)
    grp.remove('value')
    exp = exp.groupby(grp).sum().reset_index()
    exp = exp[columns]

    obs = df.map_regions('r5_region', region_col='iso', agg='sum').data

    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_48b():
    # tests fix for #48 mapping few->many

    exp = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'SSD', 'var', 'unit', 1, 6],
        ['model', 'scen', 'SDN', 'var', 'unit', 1, 6],
        ['model', 'scen1', 'SSD', 'var', 'unit', 2, 7],
        ['model', 'scen1', 'SDN', 'var', 'unit', 2, 7],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    )).data.reset_index(drop=True)

    df = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'R5MAF', 'var', 'unit', 1, 6],
        ['model', 'scen1', 'R5MAF', 'var', 'unit', 2, 7],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    ))
    obs = df.map_regions('iso', region_col='r5_region').data
    obs = obs[obs.region.isin(['SSD', 'SDN'])].reset_index(drop=True)

    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_48c():
    # tests fix for #48 mapping few->many, dropping duplicates

    exp = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'AGO', 'var', 'unit', 1, 6],
        ['model', 'scen1', 'AGO', 'var', 'unit', 2, 7],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    )).data.reset_index(drop=True)

    df = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'R5MAF', 'var', 'unit', 1, 6],
        ['model', 'scen1', 'R5MAF', 'var', 'unit', 2, 7],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    ))
    obs = df.map_regions('iso', region_col='r5_region',
                         remove_duplicates=True).data
    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_rename_variable():
    df = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'SST', 'test_1', 'unit', 1, 5],
        ['model', 'scen', 'SDN', 'test_2', 'unit', 2, 6],
        ['model', 'scen', 'SST', 'test_3', 'unit', 3, 7],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    ))

    mapping = {'variable': {'test_1': 'test', 'test_3': 'test'}}

    obs = df.rename(mapping).data.reset_index(drop=True)

    exp = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'SST', 'test', 'unit', 4, 12],
        ['model', 'scen', 'SDN', 'test_2', 'unit', 2, 6],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    )).data.sort_values(by='region').reset_index(drop=True)

    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_rename_index_fail(meta_df_iam):
    mapping = {'scenario': {'a_scenario': 'a_scenario2'}}
    pytest.raises(ValueError, meta_df_iam.rename, mapping)


def test_rename_index(meta_df_iam):
    mapping = {'model': {'a_model': 'b_model'},
               'scenario': {'a_scenario': 'b_scen'}}
    obs = meta_df_iam.rename(mapping)

    # test data changes
    exp = pd.DataFrame([
        ['b_model', 'b_scen', 'World', 'Primary Energy', 'EJ/y', 1., 6.],
        ['b_model', 'b_scen', 'World', 'Primary Energy|Coal', 'EJ/y', .5, 3.],
        ['b_model', 'a_scenario2', 'World', 'Primary Energy', 'EJ/y', 2., 7.],
    ], columns=['model', 'scenario', 'region', 'variable', 'unit', 2005, 2010]
    ).set_index(IAMC_IDX).sort_index()
    exp.columns = exp.columns.map(int)
    pd.testing.assert_frame_equal(obs.timeseries().sort_index(), exp)

    # test meta changes
    exp = pd.DataFrame([
        ['b_model', 'b_scen', False],
        ['b_model', 'a_scenario2', False],
    ], columns=['model', 'scenario', 'exclude']
    ).set_index(META_IDX)
    pd.testing.assert_frame_equal(obs.meta, exp)


def test_convert_unit():
    df = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'SST', 'test_1', 'A', 1, 5],
        ['model', 'scen', 'SDN', 'test_2', 'unit', 2, 6],
        ['model', 'scen', 'SST', 'test_3', 'C', 3, 7],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    ))

    unit_conv = {'A': ['B', 5], 'C': ['D', 3]}

    obs = df.convert_unit(unit_conv).data.reset_index(drop=True)

    exp = IamDataFrame(pd.DataFrame([
        ['model', 'scen', 'SST', 'test_1', 'B', 5, 25],
        ['model', 'scen', 'SDN', 'test_2', 'unit', 2, 6],
        ['model', 'scen', 'SST', 'test_3', 'D', 9, 21],
    ], columns=['model', 'scenario', 'region',
                'variable', 'unit', 2005, 2010],
    )).data.reset_index(drop=True)

    pd.testing.assert_frame_equal(obs, exp, check_index_type=False)


def test_pd_filter_by_meta(meta_df_iam):
    data = df_filter_by_meta_matching_idx.set_index(['model', 'region'])

    meta_df_iam.set_meta([True, False], 'boolean')
    meta_df_iam.set_meta(0, 'integer')

    obs = filter_by_meta(data, meta_df_iam, join_meta=True,
                         boolean=True, integer=None)
    obs = obs.reindex(columns=['scenario', 'col', 'boolean', 'integer'])

    exp = data.iloc[0:2].copy()
    exp['boolean'] = True
    exp['integer'] = 0

    pd.testing.assert_frame_equal(obs, exp)


def test_pd_filter_by_meta_no_index(meta_df_iam):
    data = df_filter_by_meta_matching_idx

    meta_df_iam.set_meta([True, False], 'boolean')
    meta_df_iam.set_meta(0, 'int')

    obs = filter_by_meta(data, meta_df_iam, join_meta=True,
                         boolean=True, int=None)
    obs = obs.reindex(columns=META_IDX + ['region', 'col', 'boolean', 'int'])

    exp = data.iloc[0:2].copy()
    exp['boolean'] = True
    exp['int'] = 0

    pd.testing.assert_frame_equal(obs, exp)


def test_pd_filter_by_meta_nonmatching_index(meta_df_iam):
    data = df_filter_by_meta_nonmatching_idx
    meta_df_iam.set_meta(['a', 'b'], 'string')

    obs = filter_by_meta(data, meta_df_iam, join_meta=True, string='b')
    obs = obs.reindex(columns=['scenario', 2010, 2020, 'string'])

    exp = data.iloc[2:3].copy()
    exp['string'] = 'b'

    pd.testing.assert_frame_equal(obs, exp)


def test_pd_join_by_meta_nonmatching_index(meta_df_iam):
    data = df_filter_by_meta_nonmatching_idx
    meta_df_iam.set_meta(['a', 'b'], 'string')

    obs = filter_by_meta(data, meta_df_iam, join_meta=True, string=None)
    obs = obs.reindex(columns=['scenario', 2010, 2020, 'string'])

    exp = data.copy()
    exp['string'] = [np.nan, np.nan, 'b']

    pd.testing.assert_frame_equal(obs.sort_index(level=1), exp)


@pytest.mark.xfail(reason="cast_years_to_int isn't actually casting, rather just checking that if you cast years to int, you end up with the same thing, without actually returning the cast values")
def test_iam_df_year_axis_to_int(test_df_iam):
    float_time_df = test_df_iam.data.copy()
    float_time_df.year = float_time_df.year.astype(float)
    test_df = IamDataFrame(data=float_time_df)

    # see here for explanation of numpy data type hierarchy
    # https://docs.scipy.org/doc/numpy/reference/arrays.scalars.html
    # the first assertion is a sanity check
    assert test_df_iam.data.year.dtype <= np.integer
    assert test_df.data.year.dtype <= np.integer

def test_iam_df_year_axis_must_be_int_like(float_time_pd_df):
    # int_like because of comment above re what `cast_years_to_int` actually does
    with pytest.raises(ValueError, match=re.escape("invalid values ") + r"`.*`"):
        test_df = IamDataFrame(data=float_time_pd_df)


def test_iam_df_time_axis_input_error(float_time_pd_df):
    float_time_pd_df.rename({"year": "time"}, axis="columns", inplace=True)
    with pytest.raises(ValueError):
        test_df = IamDataFrame(data=float_time_pd_df)


def test_openscm_df_time_axis_is_float(float_time_pd_df):
    float_time_pd_df.rename({"year": "time"}, axis="columns", inplace=True)
    test_df = OpenSCMDataFrame(data=float_time_pd_df)
    assert test_df.data.time.dtype <= np.float


def test_openscm_df_year_axis_input_conversion(float_time_pd_df):
    test_df = OpenSCMDataFrame(data=float_time_pd_df)
    assert test_df.data.time.dtype <= np.float
    assert "year" not in test_df.data.columns


@pytest.mark.xfail(reason="rename requires using LONG_IDX which contains year key")
def test_openscm_df_rename(test_df_openscm):
    test_df_openscm.rename({"model": {"a_model": "b_model"}})
    assert (test_df_openscm.models() == "b_model").all()


@pytest.mark.parametrize("error_cls", [Exception, KeyError, AttributeError])
def test_worst_case_conversion_error_to_openscm(test_df_iam, error_cls):
    test_df_iam._get_openscm_df_data_except_year_renaming_and_metadata = Mock(side_effect=error_cls("Test"))
    error_msg = (
        re.escape("I don't know why, but I can't convert to an OpenSCMDataFrame.")
        + r"\n"
        + re.escape("The original traceback is:")
        + r"\n[\s\S]*Test[\s\S]*"
    )
    with pytest.raises(ConversionError, match=error_msg):
        test_df_iam.to_openscm_df()


def test_to_openscm_df(test_df_iam):
    exp = pd.DataFrame([
        ['N/A', 'a_scenario|a_model', 'World', 'Primary Energy', 'EJ/y', 2005, 1],
        ['N/A', 'a_scenario|a_model', 'World', 'Primary Energy', 'EJ/y', 2010, 6.],
        ['N/A', 'a_scenario|a_model', 'World', 'Primary Energy|Coal', 'EJ/y', 2005, 0.5],
        ['N/A', 'a_scenario|a_model', 'World', 'Primary Energy|Coal', 'EJ/y', 2010, 3],
    ],
        columns=['model', 'scenario', 'region', 'variable', 'unit', 'time', 'value'],
    )

    obs = test_df_iam.to_openscm_df()
    assert obs.data.time.dtype <= np.float
    pd.testing.assert_frame_equal(obs.data, exp, check_index_type=False)


def test_to_from_openscm_df_loop(test_df_iam):
    obs = test_df_iam.to_openscm_df().to_iam_df()

    exp_df = test_df_iam.data.reset_index(drop=True)
    pd.testing.assert_frame_equal(obs.data, exp_df)
    pd.testing.assert_frame_equal(obs.meta, test_df_iam.meta)


def test_to_iam_df(test_df_openscm):
    exp = pd.DataFrame([
        ['N/A', 'a_scenario', 'World', 'Diagnostics|a_model|Primary Energy', 'EJ/y', 2005, 1],
        ['N/A', 'a_scenario', 'World', 'Diagnostics|a_model|Primary Energy', 'EJ/y', 2010, 6.],
        ['N/A', 'a_scenario', 'World', 'Diagnostics|a_model|Primary Energy|Coal', 'EJ/y', 2005, 0.5],
        ['N/A', 'a_scenario', 'World', 'Diagnostics|a_model|Primary Energy|Coal', 'EJ/y', 2010, 3],
    ],
        columns=['model', 'scenario', 'region', 'variable', 'unit', 'year', 'value'],
    )

    obs = test_df_openscm.to_iam_df()
    pd.testing.assert_frame_equal(obs.data, exp, check_index_type=False)


def test_worst_case_conversion_error_to_iam(test_df_openscm):
    test_df_openscm._get_iam_df_data_and_metadata = Mock(side_effect=Exception("Test"))
    error_msg = (
        re.escape("I don't know why, but I can't convert to an IamDataFrame.")
        + r"\n"
        + re.escape("The original traceback is:")
        + r"\n[\s\S]*Test[\s\S]*"
    )
    with pytest.raises(ConversionError, match=error_msg):
        test_df_openscm.to_iam_df()


def test_to_from_iam_df_loop(test_df_openscm):
    obs = test_df_openscm.to_iam_df().to_openscm_df()

    exp_df = test_df_openscm.data.reset_index(drop=True)
    pd.testing.assert_frame_equal(obs.data, exp_df)
    pd.testing.assert_frame_equal(obs.meta, test_df_openscm.meta)


def test_to_iam_df_missing_scenario(test_df_openscm):
    test_df_openscm.data.drop("scenario", axis="columns", inplace=True)

    error_msg = re.escape("missing required columns `['scenario']`!")
    with pytest.raises(ConversionError, match=error_msg):
        test_df_openscm.to_iam_df().to_openscm_df()


def test_to_iam_df_missing_model(test_df_openscm):
    test_df_openscm.data.drop("model", axis="columns", inplace=True)

    error_msg = re.escape("missing required columns `['model']`!")
    with pytest.raises(ConversionError, match=error_msg):
        test_df_openscm.to_iam_df().to_openscm_df()

