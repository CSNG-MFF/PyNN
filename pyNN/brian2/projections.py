# encoding: utf-8
"""

"""

from itertools import chain
from collections import defaultdict
import numpy
import brian2
from brian2 import uS, nA, mV, ms, amp, siemens, second, namp
from pyNN import common
from pyNN.standardmodels.synapses import TsodyksMarkramSynapse
from pyNN.core import is_listlike
from pyNN.parameters import ParameterSpace, simplify
from pyNN.space import Space
from . import simulator
from .standardmodels.synapses import StaticSynapse


class Connection(common.Connection):
    """
    Store an individual plastic connection and information about it. Provide an
    interface that allows access to the connection's weight, delay and other
    attributes.
    """

    def __init__(self, projection, i_group, j_group, index):
        self.projection = projection
        self.i_group = i_group
        self.j_group = j_group
        self.index = index

    # todo: implement translation properly
    def _set_weight(self, w):
        self.projection._brian2_synapses[self.i_group][self.j_group].weight[self.index] = w * 1e-6

    def _get_weight(self):
        """Synaptic weight in nA or µS."""
        return self.projection._brian2_synapses[self.i_group][self.j_group].weight[self.index] * 1e6

    def _set_delay(self, d):
        self.projection._brian2_synapses[self.i_group][self.j_group].delay[self.index] = d * 1e-3

    def _get_delay(self):
        """Synaptic delay in ms."""
        return self.projection._brian2_synapses[self.i_group][self.j_group].delay[self.index] * 1e3

    weight = property(_get_weight, _set_weight)
    delay = property(_get_delay, _set_delay)

    def as_tuple(self, *attribute_names):
        # should return indices, not IDs for source and target
        return tuple([getattr(self, name) for name in attribute_names])


class Projection(common.Projection):
    __doc__ = common.Projection.__doc__
    _simulator = simulator
    _static_synapse_class = StaticSynapse

    def __init__(self, presynaptic_population, postsynaptic_population,
                 connector, synapse_type=None, source=None, receptor_type=None,
                 space=Space(), label=None):
        common.Projection.__init__(self, presynaptic_population, postsynaptic_population,
                                   connector, synapse_type, source, receptor_type,
                                   space, label)
        self._n_connections = 0
        # create one Synapses object per pre-post population pair
        # there will be multiple such pairs if either `presynaptic_population`
        # or `postsynaptic_population` is an Assembly.
        if isinstance(self.pre, common.Assembly):
            presynaptic_populations = self.pre.populations
        else:
            presynaptic_populations = [self.pre]
        if isinstance(self.post, common.Assembly):
            postsynaptic_populations = self.post.populations
            assert self.post._homogeneous_synapses, "Inhomogeneous assemblies not yet supported"
        else:
            postsynaptic_populations = [self.post]
        self._brian2_synapses = defaultdict(dict)
        for i, pre in enumerate(presynaptic_populations):
            for j, post in enumerate(postsynaptic_populations):
                # complete the synapse type equations according to the
                # post-synaptic response type
                psv = post.celltype.post_synaptic_variables[self.receptor_type]
                if hasattr(post.celltype, "voltage_based_synapses") and post.celltype.voltage_based_synapses:
                    weight_units = mV
                else:
                    weight_units = post.celltype.conductance_based and siemens or amp #and uS or nA
                self.synapse_type._set_target_type(weight_units)
                equation_context = {"syn_var": psv, "weight_units": weight_units}
                pre_eqns = self.synapse_type.pre % equation_context
                if self.synapse_type.post:
                    post_eqns = self.synapse_type.post % equation_context
                else:
                    post_eqns = None
                  
                model = self.synapse_type.eqs % equation_context # units are being transformed for exemple from amp to A
                #if (model=='weight : A'):
                #    model= 'weight : amp' 

                # A for ampere and S for siemens not recognised
                if model.find('weight : S') != -1:
                    model = model.replace('weight : S', 'weight : siemens')
                elif model.find('weight : A') != -1:
                    model = model.replace('weight : A', 'weight : amp')

                # create the brian2 Synapses object.
                syn_obj = brian2.Synapses(pre.brian2_group, post.brian2_group,
                                         model=model, on_pre=pre_eqns,
                                         on_post=post_eqns)
                                         #code_namespace={"exp": numpy.exp})                       
                self._brian2_synapses[i][j] = syn_obj
                simulator.state.network.add(syn_obj)
        # connect the populations
        #syn_obj.connect() ##### 
        connector.connect(self)
        #syn_obj.weight=0.3*nA
        # special-case: the Tsodyks-Markram short-term plasticity model takes
        #               a parameter value from the post-synaptic response model
        if isinstance(self.synapse_type, TsodyksMarkramSynapse):
            self._set_tau_syn_for_tsodyks_markram()

    def __len__(self):
        return self._n_connections

    @property
    def connections(self):
        """
        Returns an iterator over local connections in this projection, as `Connection` objects.
        """
        return (Connection(self, i_group, j_group, i)
                for i_group in range(len(self._brian2_synapses))
                for j_group in range(len(self._brian2_synapses[i_group]))
                for i in range(len(self._brian2_synapses[i_group][j_group]))
                )

    def _partition(self, indices):
        """
        partition indices, in case of Assemblies
        """
        if isinstance(self.pre, common.Assembly):
            boundaries = numpy.cumsum([0] + [p.size for p in self.pre.populations])
            assert indices.max() < boundaries[-1]
            partitions = numpy.split(indices, numpy.searchsorted(indices, boundaries[1:-1])) - boundaries[:-1]
            for i_group, local_indices in enumerate(partitions):
                if isinstance(self.pre.populations[i_group], common.PopulationView):
                    partitions[i_group] = self.pre.populations[i_group].index_in_grandparent(local_indices)
        elif isinstance(self.pre, common.PopulationView):
            partitions = [self.pre.index_in_grandparent(indices)]
        else:
            partitions = [indices]
        return partitions

    def _localize_index(self, index):
        """determine which group the postsynaptic index belongs to """
        if isinstance(self.post, common.Assembly):
            boundaries = numpy.cumsum([0] + [p.size for p in self.post.populations])
            j = numpy.searchsorted(boundaries, index, side='right') - 1
            local_index = index - boundaries[j]
            if isinstance(self.post.populations[j], common.PopulationView):
                return j, self.post.populations[j].index_in_grandparent(local_index)
            else:
                return j, local_index
        elif isinstance(self.post, common.PopulationView):
            return 0, self.post.index_in_grandparent(index)
        else:
            return 0, index

    def _convergent_connect(self, presynaptic_indices, postsynaptic_index,
                            **connection_parameters):               
        connection_parameters.pop("dendritic_delay_fraction", None)  # TODO: need to to handle this
        presynaptic_index_partitions = self._partition(presynaptic_indices)
        j_group, j = self._localize_index(postsynaptic_index)
        # specify which connections exist
        for i_group, i in enumerate(presynaptic_index_partitions):
            if i.size > 0:
                self._brian2_synapses[i_group][j_group].connect(i=i, j=j) #####"[i, j]
                self._n_connections += i.size
        # set connection parameters
       
        for name, value in chain(connection_parameters.items(),
                                 self.synapse_type.initial_conditions.items()):                                                        
            if name == 'delay':
                scale = self._simulator.state.dt * ms
                value /= scale                         # ensure delays are rounded to the
                value = numpy.round(value) * scale     # nearest time step, rather than truncated   
            for i_group, i in enumerate(presynaptic_index_partitions):
                if i.size > 0:
                    brian2_var = getattr(self._brian2_synapses[i_group][j_group], name)
                    if is_listlike(value):
                        for ii, v in zip(i, value):
                            if (name=="weight"):
                                if(self.pre.conductance_based==True):
                                    brian2_var[ii, j] = v * siemens
                                else:
                                    brian2_var[ii, j] = v * namp
                            elif name == "tau_rec":  # find better solution here
                                brian2_var[ii, j] = v * second
                            else:
                                brian2_var[ii, j] = v
                    else:
                        for ii in i:
                            if (name == "delay"):
                                brian2_var[ii, j] = value * second
                            if (name=="w_min" or name=="w_max"):    
                                brian2_var[ii, j] = value * namp
                            if (name=="weight"):
                                if(self.pre.conductance_based==True):
                                    brian2_var[ii, j] = value * siemens
                                else:
                                    brian2_var[ii, j] = value * namp    
                            if (name=="tau_facil" or name=="tau_rec" or name=="tau_plus" or name=="tau_minus"):    
                                brian2_var[ii, j] = value * second 
                            if(name=="U" or name=="A_plus" or name=="A_minus"):
                                brian2_var[ii, j] = value
                    ##brian2_var[i, j] = value  # doesn't work with multiple connections between a given neuron pair. Need to understand the internals of Synapses and SynapticVariable better

    def _set_attributes(self, connection_parameters):
        if isinstance(self.post, common.Assembly) or isinstance(self.pre, common.Assembly):
            raise NotImplementedError  
        syn_obj = self._brian2_synapses[0][0]
        slice_value= syn_obj.weight.shape[0]
        connection_parameters.evaluate()  # inefficient: would be better to evaluate using mask
        for name, value in connection_parameters.items():
            value = value.T
            filtered_value= numpy.ravel(value)
            filtered_value=filtered_value[0: slice_value]
            if(name=='w_min' or name=='w_max'):
                filtered_value= filtered_value * namp
            if (name=="weight"):
                if(self.pre.conductance_based==True):
                    filtered_value = filtered_value * siemens
                else:
                    filtered_value = filtered_value * namp        
            if(name=='delay'):
                filtered_value= filtered_value * second   
            if (name=="tau_facil" or name=="tau_rec" or name=="tau_plus" or name=="tau_minus"):
                filtered_value= filtered_value * second 
            if(name=="U" or name=="A_plus" or name=="A_minus"):
                filtered_value= filtered_value        

            setattr(syn_obj, name, filtered_value)

    def _get_attributes_as_arrays(self, attribute_names, multiple_synapses='sum'):
        if isinstance(self.post, common.Assembly) or isinstance(self.pre, common.Assembly):
            raise NotImplementedError
        values = []
        
        for name in attribute_names:
            value = getattr(self._brian2_synapses[0][0], name)#.to_matrix(multiple_synapses=multiple_synapses)
            if name == 'delay':
                value *= self._simulator.state.dt * ms
            ps = self.synapse_type.reverse_translate(ParameterSpace({name: value}, shape=value.shape))  # should really use the translated name
            ps.evaluate()
            value = ps[name]
            values.append(value)
        # todo: implement parameter translation
        return values  # should put NaN where there is no connection?

    def _get_attributes_as_list(self, attribute_names):
        if isinstance(self.post, common.Assembly) or isinstance(self.pre, common.Assembly):
            raise NotImplementedError
        values = []
        slice_value= self._brian2_synapses[0][0].weight.shape[0]
        print(self._brian2_synapses[0][0]._indices)
        for name in attribute_names:
            if name == "presynaptic_index":
                value = self._brian2_synapses[0][0]._indices.synaptic_pre.get_value()
            elif name == "postsynaptic_index":
                value=self._brian2_synapses[0][0]._indices.synaptic_post.get_value()
            else:
                data_obj1 = getattr(self._brian2_synapses[0][0], name)
                data_obj = data_obj1[slice(0,slice_value,None)]
                
                if hasattr(data_obj, "tolist"):
                    value = data_obj
                else:
                    assert name == 'delay'
                    value = data_obj.data * self._simulator.state.dt * ms
                ps = self.synapse_type.reverse_translate(ParameterSpace({name: value}, shape=value.shape))  # should really use the translated name
                # this whole "get attributes" thing needs refactoring in all backends to properly use translation
                ps.evaluate()
                value = ps[name]
            #value = value.tolist()
            values.append(value)
        a = numpy.array(values)
        
        return [tuple(x) for x in a.T]

    def _set_tau_syn_for_tsodyks_markram(self):
        if isinstance(self.post, common.Assembly) or isinstance(self.pre, common.Assembly):
            raise NotImplementedError
        tau_syn_var = self.synapse_type.tau_syn_var[self.receptor_type]
        self._brian2_synapses[0][0].tau_syn = self.post.get(tau_syn_var)[self._brian2_synapses[0][0].j] * brian2.ms
