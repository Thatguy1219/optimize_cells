"""
Tools for pulling individual neurons out of the dentate network simulation environment for single-cell tuning.
"""
__author__ = 'Ivan Raikov, Grace Ng, Aaron D. Milstein'
import os.path
import click
try:
    from mpi4py import MPI  # Must come before importing NEURON
except Exception:
    pass
import h5py
from neuron import h
from neuroh5.h5py_io_utils import *
from dentate.env import Env
from dentate.cells import *
from dentate.synapses import *
from dentate.neuron_utils import *
from nested.utils import *


context = Context()


class QuickSim(object):
    """
    This method is used to run a quick simulation with a set of current injections and a set of recording sites.
    Can save detailed information about the simulation to an HDF5 file after each run. Once defined, IClamp objects
    persist when using an interactive console, but not when executing standalone scripts. Therefore, the best practice
    is simply to set amp to zero to turn off current injections, or move individual IClamp processes to different
    locations rather then adding and deleting them.
    class params:
    self.stim_list:
    self.rec_list:
    """

    def __init__(self, tstop=400., cvode=True, daspk=False, dt=None, verbose=True):
        """

        :param tstop: float
        :param cvode: bool
        :param daspk: bool
        :param dt: float
        :param verbose: bool
        """
        self.rec_list = []  # list of dicts with keys for 'cell', 'node', 'loc' and 'vec': pointer to hoc Vector object.
        # Also contains keys for 'ylabel' and 'units' for recording parameters other than Vm.
        self.stim_list = []  # list of dicts with keys for 'cell', 'node', 'stim': pointer to hoc IClamp object, and
        # 'vec': recording of actual stimulus for plotting later
        self.tstop = tstop
        h.load_file('stdrun.hoc')
        h.celsius = 35.0
        h.cao0_ca_ion = 1.3
        self.cvode = h.CVode()
        self.cvode_atol = 0.01  # 0.001
        self.daspk = daspk
        self.cvode_state = cvode
        if dt is None:
            self.dt = h.dt
        else:
            self.dt = dt
        self.verbose = verbose
        self.tvec = h.Vector()
        self.tvec.record(h._ref_t, self.dt)
        self.parameters = {}

    def run(self, v_init=-65.):
        """

        :param v_init: float
        """
        start_time = time.time()
        h.tstop = self.tstop
        if not self.cvode_state:
            h.steps_per_ms = int(1. / self.dt)
            h.dt = self.dt
        h.v_init = v_init
        # h.init()
        # h.finitialize(v_init)
        # if self.cvode_state:
        #     self.cvode.re_init()
        # else:
        #     h.fcurrent()
        h.run()
        if self.verbose:
            print 'Simulation runtime: ', time.time() - start_time, ' sec'

    def append_rec(self, cell, node, loc=None, param='_ref_v', object=None, ylabel='Vm', units='mV', description=None):
        """

        :param cell: :class:'BiophysCell'
        :param node: :class:'SHocNode
        :param loc: float
        :param param: str
        :param object: :class:'HocObject'
        :param ylabel: str
        :param units: str
        :param description: str
        """
        rec_dict = {'cell': cell, 'node': node, 'ylabel': ylabel, 'units': units}
        if description is None:
            rec_dict['description'] = 'rec' + str(len(self.rec_list))
        elif description in (rec['description'] for rec in self.rec_list):
            rec_dict['description'] = description + str(len(self.rec_list))
        else:
            rec_dict['description'] = description
        rec_dict['vec'] = h.Vector()
        if object is None:
            if loc is None:
                loc = 0.5
            rec_dict['vec'].record(getattr(node.sec(loc), param), self.dt)
        else:
            if loc is None:
                try:
                    loc = object.get_segment().x  # this should not push the section to the hoc stack or risk overflow
                except:
                    loc = 0.5  # if the object doesn't have a .get_loc() method, default to 0.5
            if param is None:
                rec_dict['vec'].record(object, self.dt)
            else:
                rec_dict['vec'].record(getattr(object, param), self.dt)
        rec_dict['loc'] = loc
        self.rec_list.append(rec_dict)

    def get_rec(self, description):
        """
        Return the dict corresponding to the item in the rec_dict list with the specified description.
        :param description: str
        :return: dict
        """
        for rec in self.rec_list:
            if rec['description'] == description:
                return rec
        raise Exception('No recording with description %s' % description)

    def get_rec_index(self, description):
        """
        Return the index of the item in the rec_dict list with the specified description.
        :param description: str
        :return: dict
        """
        for i, rec in enumerate(self.rec_list):
            if rec['description'] == description:
                return i
        raise Exception('No recording with description %s' % description)

    def append_stim(self, cell, node, loc, amp, delay, dur, description='IClamp'):
        """

        :param cell: :class:'BiophysCell'
        :param node: :class:'SHocNode'
        :param loc: float
        :param amp: float
        :param delay: float
        :param dur: float
        :param description: str
        """
        stim_dict = {'cell': cell, 'node': node, 'description': description}
        stim_dict['stim'] = h.IClamp(node.sec(loc))
        stim_dict['stim'].amp = amp
        stim_dict['stim'].delay = delay
        stim_dict['stim'].dur = dur
        stim_dict['vec'] = h.Vector()
        stim_dict['vec'].record(stim_dict['stim']._ref_i, self.dt)
        self.stim_list.append(stim_dict)

    def modify_stim(self, index=0, node=None, loc=None, amp=None, delay=None, dur=None, description=None):
        """

        :param index: int
        :param node: class:'SHocNode'
        :param loc: float
        :param amp: float
        :param delay: float
        :param dur: float
        :param description: str
        """
        stim_dict = self.stim_list[index]
        if not (node is None and loc is None):
            if not node is None:
                stim_dict['node'] = node
            if loc is None:
                loc = stim_dict['stim'].get_segment().x
            stim_dict['stim'].loc(stim_dict['node'].sec(loc))
        if not amp is None:
            stim_dict['stim'].amp = amp
        if not delay is None:
            stim_dict['stim'].delay = delay
        if not dur is None:
            stim_dict['stim'].dur = dur
        if not description is None:
            stim_dict['description'] = description

    def get_stim_index(self, description):
        """
        Return the index of the item in the stim_dict list with the specified description.
        :param description: str
        :return: dict
        """
        for i, stim in enumerate(self.stim_list):
            if stim['description'] == description:
                return i
        raise Exception('No IClamp object with description: %s' % description)

    def modify_rec(self, index=0, node=None, loc=None, object=None, param='_ref_v', ylabel=None, units=None,
                   description=None):
        """

        :param index: int
        :param node: class:'SHocNode'
        :param loc: float
        :param object: class:'HocObject'
        :param param: str
        :param ylabel: str
        :param units: str
        :param description: str
        """
        rec_dict = self.rec_list[index]
        if not ylabel is None:
            rec_dict['ylabel'] = ylabel
        if not units is None:
            rec_dict['units'] = units
        if not node is None:
            rec_dict['node'] = node
        if not loc is None:
            rec_dict['loc'] = loc
        if object is None:
            rec_dict['vec'].record(getattr(rec_dict['node'].sec(rec_dict['loc']), param), self.dt)
        elif param is None:
            rec_dict['vec'].record(object, self.dt)
        else:
            rec_dict['vec'].record(getattr(object, param), self.dt)
        if not description is None:
            rec_dict['description'] = description

    def plot(self):
        """

        """
        for rec_dict in self.rec_list:
            if 'description' in rec_dict:
                description = str(rec_dict['description'])
            else:
                description = ''
            plt.plot(self.tvec, rec_dict['vec'], label=rec_dict['node'].name + '(' + str(rec_dict['loc']) + ') - ' +
                                                       description)
            plt.xlabel("Time (ms)")
            plt.ylabel(rec_dict['ylabel'] + ' (' + rec_dict['units'] + ')')
        plt.legend(loc='upper right')
        if 'description' in self.parameters:
            plt.title(self.parameters['description'])
        plt.show()
        plt.close()

    def export_to_file(self, f, simiter=None):
        """
        Extracts important parameters from the lists of stimulation and recording sites, and exports to an HDF5
        file. Arrays are saved as datasets and metadata is saved as attributes.
        :param f: :class:'h5py.File'
        :param simiter: int
        """
        start_time = time.time()
        if 'sim_output' not in f:
            f.create_group('sim_output')
            f['sim_output'].attrs['enumerated'] = True
        target = f['sim_output']
        if simiter is None:
            simiter = len(target)
        if str(simiter) not in target:
            target.create_group(str(simiter))
        target[str(simiter)].create_dataset('time', compression='gzip', compression_opts=9, data=self.tvec)
        target[str(simiter)]['time'].attrs['dt'] = self.dt
        for parameter in self.parameters:
            target[str(simiter)].attrs[parameter] = self.parameters[parameter]
        if self.stim_list:
            target[str(simiter)].create_group('stim')
            for index, stim in enumerate(self.stim_list):
                stim_out = target[str(simiter)]['stim'].create_dataset(str(index), compression='gzip',
                                                                       compression_opts=9, data=stim['vec'])
                cell = stim['cell']
                stim_out.attrs['cell'] = cell.gid
                node = stim['node']
                stim_out.attrs['index'] = node.index
                stim_out.attrs['type'] = node.type
                loc = stim['stim'].get_segment().x
                stim_out.attrs['loc'] = loc
                distance = get_distance_to_node(cell, cell.tree.root, node, loc)
                stim_out.attrs['soma_distance'] = distance
                distance = get_distance_to_node(cell, get_dendrite_origin(cell, node), node, loc)
                stim_out.attrs['branch_distance'] = distance
                stim_out.attrs['amp'] = stim['stim'].amp
                stim_out.attrs['delay'] = stim['stim'].delay
                stim_out.attrs['dur'] = stim['stim'].dur
                stim_out.attrs['description'] = stim['description']
        target[str(simiter)].create_group('rec')
        for index, rec in enumerate(self.rec_list):
            rec_out = target[str(simiter)]['rec'].create_dataset(str(index), compression='gzip', compression_opts=9,
                                                            data=rec['vec'])
            cell = rec['cell']
            rec_out.attrs['cell'] = cell.gid
            node = rec['node']
            rec_out.attrs['index'] = node.index
            rec_out.attrs['type'] = node.type
            rec_out.attrs['loc'] = rec['loc']
            distance = get_distance_to_node(cell, cell.tree.root, node, rec['loc'])
            rec_out.attrs['soma_distance'] = distance
            distance = get_distance_to_node(cell, get_dendrite_origin(cell, node), node, rec['loc'])
            node_is_terminal = int(is_terminal(node))
            branch_order = get_branch_order(cell, node)
            rec_out.attrs['branch_distance'] = distance
            rec_out.attrs['is_terminal'] = node_is_terminal
            rec_out.attrs['branch_order'] = branch_order
            rec_out.attrs['ylabel'] = rec['ylabel']
            rec_out.attrs['units'] = rec['units']
            if 'description' in rec:
                rec_out.attrs['description'] = rec['description']
        if self.verbose:
            print 'Simulation ', simiter, ': exporting took: ', time.time() - start_time, ' s'

    def get_cvode_state(self):
        """

        :return bool
        """
        return bool(self.cvode.active())

    def set_cvode_state(self, state):
        """

        :param state: bool
        """
        if state:
            self.cvode.active(1)
            self.cvode.atol(self.cvode_atol)
            self.cvode.use_daspk(int(self.daspk))
        else:
            self.cvode.active(0)

    cvode_state = property(get_cvode_state, set_cvode_state)


def make_hoc_cell(env, gid, population):
    """

    :param env:
    :param gid:
    :param population:
    :return:
    """
    popName = population
    datasetPath = env.datasetPath
    dataFilePath = env.dataFilePath
    env.load_cell_template(popName)
    templateClass = getattr(h, env.celltypes[popName]['template'])

    if env.cellAttributeInfo.has_key(popName) and env.cellAttributeInfo[popName].has_key('Trees'):
        tree = select_tree_attributes(gid, env.comm, dataFilePath, popName)
        i = h.numCells
        hoc_cell = make_neurotree_cell(templateClass, neurotree_dict=tree, gid=gid, local_id=i,
                                             dataset_path=datasetPath)
        h.numCells = h.numCells + 1
    else:
        raise Exception('make_hoc_cell: data file: %s does not contain morphology for population: %s, gid: %i' %
                        dataFilePath, popName, gid)
    return hoc_cell


def configure_env(env):
    """

    :param env: :class:'Env'
    """
    h.load_file("nrngui.hoc")
    h.load_file("loadbal.hoc")
    h('objref fi_status, fi_checksimtime, pc, nclist, nc, nil')
    h('strdef datasetPath')
    h('numCells = 0')
    h('totalNumCells = 0')
    h.nclist = h.List()
    h.datasetPath = env.datasetPath
    h.pc = h.ParallelContext()
    env.pc = h.pc
    ## polymorphic value template
    h.load_file(env.hoclibPath + '/templates/Value.hoc')
    ## randomstream template
    h.load_file(env.hoclibPath + '/templates/ranstream.hoc')
    ## stimulus cell template
    h.load_file(env.hoclibPath + '/templates/StimCell.hoc')
    h.xopen(env.hoclibPath + '/lib.hoc')

    h('objref templatePaths, templatePathValue')
    h.templatePaths = h.List()
    for path in env.templatePaths:
        h.templatePathValue = h.Value(1, path)
        h.templatePaths.append(h.templatePathValue)


def get_biophys_cell(env, gid, pop_name):
    """
    TODO: Provide options to cache 'Connection distances' and synaptic weights from file.
    :param env:
    :param gid:
    :param pop_name:
    :return:
    """
    hoc_cell = make_hoc_cell(env, gid, pop_name)
    cell = BiophysCell(gid=gid, population=pop_name, hoc_cell=hoc_cell)
    syn_attrs = env.synapse_attributes
    if pop_name not in syn_attrs.select_cell_attr_index_map:
        syn_attrs.select_cell_attr_index_map[pop_name] = \
            get_cell_attributes_index_map(env.comm, env.dataFilePath, pop_name, 'Synapse Attributes')
    syn_attrs.load_syn_id_attrs(gid, select_cell_attributes(gid, env.comm, env.dataFilePath,
                                                            syn_attrs.select_cell_attr_index_map[pop_name], pop_name,
                                                            'Synapse Attributes'))

    for source_name in env.projection_dict[pop_name]:
        if source_name not in syn_attrs.select_edge_attr_index_map[pop_name]:
            syn_attrs.select_edge_attr_index_map[pop_name][source_name] = \
                get_edge_attributes_index_map(env.comm, env.connectivityFilePath, source_name, pop_name)
        source_indexes, edge_attr_dict = \
            select_edge_attributes(gid, env.comm, env.connectivityFilePath,
                                   syn_attrs.select_edge_attr_index_map[pop_name][source_name], source_name, pop_name,
                                   ['Synapses'])
        syn_attrs.load_edge_attrs(gid, source_name, edge_attr_dict['Synapses']['syn_id'], env)
    return cell


@click.command()
@click.option("--gid", required=True, type=int, default=0)
@click.option("--pop-name", required=True, type=str, default='GC')
@click.option("--config-file", required=True, type=click.Path(exists=True, file_okay=True, dir_okay=False),
              default='../dentate/config/Small_Scale_Control_log_normal_weights.yaml')
@click.option("--template-paths", type=str, default='../dgc/Mateos-Aparicio2014:../dentate/templates')
@click.option("--hoc-lib-path", required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True),
              default='../dentate')
@click.option("--dataset-prefix", required=True, type=click.Path(exists=True, file_okay=False, dir_okay=True),
              default='../dentate/datasets')  # '/mnt/s')  # '../dentate/datasets'
@click.option("--mech-file-path", required=True, type=click.Path(exists=True, file_okay=True, dir_okay=False),
              default='mechanisms/20180209_DG_GC_hoc_leak_mech.yaml')
@click.option('--verbose', '-v', is_flag=True)
def main(gid, pop_name, config_file, template_paths, hoc_lib_path, dataset_prefix, mech_file_path, verbose):
    """

    :param gid:
    :param pop_name:
    :param config_file:
    :param template_paths:
    :param hoc_lib_path:
    :param dataset_prefix:
    :param verbose
    """
    comm = MPI.COMM_WORLD
    np.seterr(all='raise')
    env = Env(comm, config_file, template_paths, hoc_lib_path, dataset_prefix, verbose=verbose)
    configure_env(env)

    cell = get_biophys_cell(env, gid, pop_name)
    context.update(locals())

    init_biophysics(cell, reset_cable=True, from_file=True, mech_file_path=mech_file_path, correct_cm=True,
                    correct_g_pas=True, env=env)
    """

    
    #Synapses
    #subset_syn_list = [5, 10]
    subset_syn_list = context.cell_attr_dict[gid]['syn_ids']
    subset_source_names = subset_syns_by_source(subset_syn_list, context.cell_attr_dict, context.syn_index_map, gid, env)
    subset_source_names = {'MPP': subset_source_names['MPP']} #test only by making MPP synapses
    context.subset_source_names = subset_source_names
    insert_syn_subset(cell, context.syn_attrs_dict, context.cell_attr_dict, gid, subset_source_names, env, pop_name)
    """


if __name__ == '__main__':
    main(args=sys.argv[(list_find(lambda s: s.find(os.path.basename(__file__)) != -1, sys.argv) + 1):],
         standalone_mode=False)