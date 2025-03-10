# -*- coding: utf-8 -*-
"""
Definition of NativeSynapseType class for NEST

:copyright: Copyright 2006-2023 by the PyNN team, see AUTHORS.
:license: CeCILL, see LICENSE for details.
"""

import nest

from ..models import BaseSynapseType
from ..errors import NoModelAvailableError
from .simulator import state
from .conversion import make_pynn_compatible, make_sli_compatible

DEFAULT_TAU_MINUS = 20.0


def get_synapse_defaults(model_name):
    defaults = nest.GetDefaults(model_name)
    ignore = ['max_delay', 'min_delay', 'num_connections',
              'num_connectors', 'receptor_type', 'synapsemodel',
              'property_object', 'element_type', 'type', 'sizeof',
              'has_delay', 'synapse_model', 'requires_symmetric',
              'weight_recorder', 'init_flag', 'next_readout_time',
              'synapse_id', 'synapse_modelid']
    default_params = {}
    for name, value in defaults.items():
        if name not in ignore:
            default_params[name] = value
    default_params['tau_minus'] = DEFAULT_TAU_MINUS
    return default_params


class NESTSynapseMixin(object):

    def _get_nest_synapse_model(self):
        synapse_defaults = {}
        for name, value in self.native_parameters.items():
            if value.is_homogeneous:
                value.shape = (1,)
                synapse_defaults[name] = value.evaluate(simplify=True)
        synapse_defaults = make_sli_compatible(synapse_defaults)
        synapse_defaults.pop("tau_minus", None)
        try:
            nest.SetDefaults(self.nest_name + '_lbl', synapse_defaults)
        except nest.NESTError:
            if not state.extensions_loaded:
                raise NoModelAvailableError(
                    "{self.__class__.__name__} is not available."
                    "There was a problem loading NEST extensions".format(self=self)
                )
            raise
        return self.nest_name + '_lbl'

    def _get_minimum_delay(self):
        return state.min_delay

    def _set_tau_minus(self, cells):
        if len(cells) > 0 and self.has_parameter('tau_minus'):
            native_parameters = self.native_parameters
            # could allow inhomogeneous values as long as each column is internally homogeneous
            if not native_parameters["tau_minus"].is_homogeneous:
                raise ValueError(
                    "pyNN.NEST does not support tau_minus being different for different synapses")
            native_parameters.shape = (1,)
            tau_minus = native_parameters["tau_minus"].evaluate(simplify=True)
            nest.SetStatus(cells, {'tau_minus': tau_minus})


class NativeSynapseType(BaseSynapseType, NESTSynapseMixin):

    @property
    def native_parameters(self):
        return self.parameter_space

    def get_native_names(self, *names):
        return names


def native_synapse_type(model_name):
    """
    Return a new NativeSynapseType subclass.
    """
    default_parameters = get_synapse_defaults(model_name)

    default_parameters = make_pynn_compatible(default_parameters)

    return type(model_name,
                (NativeSynapseType,),
                {
                    'nest_name': model_name,
                    'default_parameters': default_parameters,
                })
