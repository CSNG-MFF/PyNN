from pyNN.standardmodels import build_translations, StandardModelType, \
    STDPWeightDependence, STDPTimingDependence
from pyNN.standardmodels.synapses import StaticSynapse, STDPMechanism
from pyNN import errors
from pyNN.parameters import ParameterSpace
try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock
import pytest
import numpy as np


def test_build_translations():
    t = build_translations(
        ('a', 'A'),
        ('b', 'B', 1000.0),
        ('c', 'C', 'c + a', 'C - A')
    )
    assert set(t.keys()) == set(['a', 'b', 'c'])
    assert set(t['a'].keys()) == set(['translated_name', 'forward_transform', 'reverse_transform', 'type'])
    assert t['a']['translated_name'] == 'A'
    assert t['a']['forward_transform'] == 'a'
    assert t['a']['reverse_transform'] == 'A'
    assert t['b']['translated_name'] == 'B'
    assert callable(t['b']['forward_transform'])
    assert t['b']['forward_transform'](b=7) == 7000
    assert callable(t['b']['reverse_transform'])
    assert t['b']['reverse_transform'](B=7000) == 7
    assert t['c']['translated_name'] == 'C'
    assert t['c']['forward_transform'] == 'c + a'
    assert t['c']['reverse_transform'] == 'C - A'


def test_has_parameter():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3}
    assert M.has_parameter('a')
    assert M.has_parameter('b')
    assert not M.has_parameter('z')


def test_get_parameter_names():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3}
    assert set(M.get_parameter_names()) == set(['a', 'b'])


def test_instantiate():
    """
    Instantiating a StandardModelType should set self.parameter_space to a
    ParameterSpace object containing the provided parameters.
    """
    M = StandardModelType
    M.default_parameters = {'a': 0.0, 'b': 0.0}
    P1 = {'a': 22.2, 'b': 33.3}
    m = M(**P1)
    assert m.parameter_space._parameters == ParameterSpace(P1, None, None)._parameters
    M.default_parameters = {}


def _parameter_space_to_dict(parameter_space, size):
    parameter_space.shape = (size,)
    parameter_space.evaluate(simplify=True)
    return parameter_space.as_dict()


def test_translate():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3, 'c': 44.4}
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 1000.0),
        ('c', 'C', 'c + a', 'C - A'),
    )
    m = M()
    native_parameters = m.translate(ParameterSpace(
        {'a': 23.4, 'b': 34.5, 'c': 45.6}, m.get_schema(), None))
    assert _parameter_space_to_dict(native_parameters, 77) == {'A': 23.4, 'B': 34500.0, 'C': 69.0}


def test_translate_with_invalid_transformation():
    M = StandardModelType
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 'b + z', 'B-Z'),
    )
    M.default_parameters = {'a': 22.2, 'b': 33.3}
    # really we should trap such errors in build_translations(), not in translate()
    m = M()
    with pytest.raises(NameError):
        m.translate(ParameterSpace({'a': 23.4, 'b': 34.5}, m.get_schema(), None))


def test_translate_with_divide_by_zero_error():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3}
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 'b/0', 'B*0'),
    )
    m = M()
    native_parameters = m.translate(ParameterSpace({'a': 23.4, 'b': 34.5}, m.get_schema(), 77))
    with pytest.raises(ZeroDivisionError):
        native_parameters.evaluate(simplify=True)


def test_reverse_translate():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3, 'c': 44.4}
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 1000.0),
        ('c', 'C', 'c + a', 'C - A'),
    )
    assert _parameter_space_to_dict(
            M().reverse_translate(
                ParameterSpace({'A': 23.4, 'B': 34500.0, 'C': 69.0})), 88
           ) == {'a': 23.4, 'b': 34.5, 'c': 45.6}


def test_reverse_translate_with_invalid_transformation():
    M = StandardModelType
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 'b + z', 'B-Z'),
    )
    M.default_parameters = {'a': 22.2, 'b': 33.3}
    # really we should trap such errors in build_translations(), not in reverse_translate()
    with pytest.raises(NameError):
        M().reverse_translate({'A': 23.4, 'B': 34.5})


def test_simple_parameters():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3, 'c': 44.4}
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 1000.0),
        ('c', 'C', 'c + a', 'C - A'),
    )
    assert M().simple_parameters() == ['a']


def test_scaled_parameters():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3, 'c': 44.4}
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 1000.0),
        ('c', 'C', 'c + a', 'C - A'),
    )
    assert M().scaled_parameters() == ['b']


def test_computed_parameters():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3, 'c': 44.4}
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 1000.0),
        ('c', 'C', 'c + a', 'C - A'),
    )
    assert M().computed_parameters() == ['c']


def test_describe():
    M = StandardModelType
    M.default_parameters = {'a': 22.2, 'b': 33.3, 'c': 44.4}
    M.translations = build_translations(
        ('a', 'A'),
        ('b', 'B', 1000.0),
        ('c', 'C', 'c + a', 'C - A'),
    )
    assert isinstance(M().describe(), str)

# test StandardCellType

# test ComposedSynapseType

# test create


def test_describe_synapse_type():
    StaticSynapse._get_minimum_delay = lambda self: 0.1
    sd = StaticSynapse()
    assert isinstance(sd.describe(), str)
    assert isinstance(sd.describe(template=None), dict)
    del StaticSynapse._get_minimum_delay


def test_STDPMechanism_create():
    STDPMechanism._get_minimum_delay = lambda self: 0.1
    STDPMechanism.base_translations = {}
    STDPTimingDependence.__init__ = Mock(return_value=None)
    STDPWeightDependence.__init__ = Mock(return_value=None)
    td = STDPTimingDependence()
    wd = STDPWeightDependence()
    stdp = STDPMechanism(td, wd, None, 0.5)
    assert stdp.timing_dependence == td
    assert stdp.weight_dependence == wd
    assert stdp.voltage_dependence == None
    assert stdp.dendritic_delay_fraction == 0.5
    del STDPMechanism._get_minimum_delay
    del STDPMechanism.base_translations


def test_STDPMechanism_create_invalid_types():
    with pytest.raises(AssertionError):  # probably want a more informative error
        STDPMechanism(timing_dependence="abc")
    with pytest.raises(AssertionError):  # probably want a more informative error
        STDPMechanism(weight_dependence="abc")
    with pytest.raises(AssertionError):  # probably want a more informative error
        STDPMechanism(dendritic_delay_fraction="abc")
    with pytest.raises(AssertionError):  # probably want a more informative error
        STDPMechanism(dendritic_delay_fraction="1.1")


# test STDPWeightDependence

# test STDPTimingDependence
