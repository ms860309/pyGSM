
class GSM(object):
    """ """

    @staticmethod
    def default_options():
        """ GSM default options. """

        if hasattr(GSM, '_default_options'): return GSM._default_options.copy()
        opt = options.Options() 

        opt.add_option(
            key='states',
            value=[(1,0)],
            required=False,
            doc='list of tuples (multiplicity,state) state is 0-indexed')

        opt.add_option(
                key='job_data',
                value={},
                required=False,
                allowed_types=[dict],
                doc='extra key-word arguments to define level of theory object. e.g.\
                     TeraChem Cloud requires a TeraChem client and options dictionary.'
                )

        opt.add_option(
                key='EST_Package',
                value=None,
                required=True,
                allowed_values=['QChem','Molpro','Orca','PyTC','OpenMM','DFTB','TCC'],
                doc='the electronic structure theory package that is being used.'
                )

        opt.add_option(
                key='xyzfile',
                required=True,
                allowed_types=[str],
                doc='xyzfile name.'
                )

        opt.add_option(
                key='PES_type',
                value='PES',
                allowed_values=['PES','Penalty_PES','Avg_PES'],
                required=False,
                doc='PES type'
                )
        opt.add_option(
                key='adiabatic_idx',
                value=0,
                required=False if len(states)==1 else True,
                doc='adiabatic index')

        opt.add_option(
                key='multiplicity',
                value=1,
                required=False if len(states)==1 else True,
                doc='multiplicity')

        opt.add_option(
                key="FORCE",
                value=None,
                required=False,
                doc='Apply a spring force between atoms in units of AU, e.g. [(1,2,0.1214)]. Negative is tensile, positive is compresive',
                )
        
          opt.add_option(
                  key='coordinate_type',
                  value='TRIC',
                  required=False,
                  allowed_values=['TRIC','DLC','HDLC'],
                  doc='the type of coordinate system, TRIC is recommended.'
                  )

          opt.add_option(
                  key='optimizer',
                  value='eigenvector_follow',
                  required=False,
                  allowed_values=['eigenvector_follow','lbfgs','conjugate_gradient'],
                  doc='The type of optimizer, eigenvector follow is recommended for non-condensed phases. L-BFGS is recommended for condensed phases.'
                  )

          opt.add_option(
                  key='opt_print_level',
                  value=1,
                  required=False,
                  doc='1 prints normal, 2 prints almost everything for optimization.'
                  )

          opt.add_option(
                  key='gsm_type',
                  value='DE-GSM',
                  required=False,
                  allowed_values=['DE_GSM','SE_GSM','SE_Cross'],
                  doc='The type of GSM to use'
                  )

          opt.add_option(
                  key='number_nodes',
                  value=9,
                  required=False,
                  doc='The number of nodes for GSM -- choose large for SE-GSM or SE-CROSS.'
                  )

          opt.add_option(
                  key='driving_coordinates',
                  value=None,
                  required=False if opt.options['gsm_type']=='DE-GSM' else True,
                  doc='List of tuples specifying coordinates to drive and to what value\
                       indexed at 1. E.g. [("BREAK",1,2,5.0)] tells break 1 2 to 5. angstrom.\
                       ADD and BREAK have default distances specified')

          #opt.add_option(
          #        key='rp_type',
          #        value='Exact_TS',
          #        required=True if opt.options['gsm_type']=='SE-CROSS' else False,
          #        allowed_values=['Exact_TS','Climb','Opt_Only','SE-MECI','SE-MESX']
          #        doc='How to optimize the string. Exact TS does an exact TS optimization,\
          #                Climb only does climbing image, Opt only does not optimize the TS,\
          #                SE-MECI and SE-MESX are for conical intersections/ISC'
          #                )

          opt.add_option(
                  key='DQMAG_MAX',
                  value=0.4,
                  required=False,
                  doc='maximum step size during growth phase for SE methods.'
                  )

          opt.add_option(
                  key='CONV_TOL',
                  value=0.0005,
                  doc='convergence tolerance for a single node.'
                  )

          opt.add_option(
                  key='gsm_print_level',
                  value=1,
                  allowed_values=[0,1,2],
                  doc='1-- normal, 2-- ?'
                  )

        opt.add_option(
            key='ADD_NODE_TOL',
            value=0.1,
            required=False,
            allowed_types=[float],
            doc='Convergence threshold before adding a new node'
            )

        opt.add_option(
                key="product_geom_fixed",
                value=True,
                required=False,
                doc="Fix last node?"
                )

        opt.add_option(
                key="growth_direction",
                value=0,
                required=False,
                doc="how to grow string,0=Normal,1=from reactant"
                )


        opt.add_option(
                key="BDIST_RATIO",
                value=0.5,
                required=False,
                doc="SE-Crossing uses this \
                        bdist must be less than 1-BDIST_RATIO of initial bdist in order to be \
                        to be considered grown.",
                        )

        opt.add_option(
                key='ID',
                value=1,
                required=False,
                doc='String identifier'

        GSM._default_options = opt
        return GSM._default_options.copy()

        
    @classmethod
    def from_options(cls,**kwargs):
        return cls(cls.default_options().set_values(kwargs))

    def __init__(
            self,
            options,
            ):
        """ Constructor """
        self.options = options

        #LOT
        printcool("Build the pyGSM level of theory (LOT) object")
        lot_class = getattr(sys.modules[__name__], options['EST_Package'])
        geom = manage_xyz.read_xyz(self.options['xyzfile1'])
        lot = lot_class.from_options(
                states=self.options['states'],
                job_data=self.options['job_data'],
                geom=geom
                )

        #PES
        printcool("Building the PES objects")
        pes_class = getattr(sys.modules[__name__], options['PES_type'])
        if pes_class=='PES':
            pes = pes_class.from_options(
                    lot=lot,
                    ad_idx=self.options['adiabatic_idx'],
                    multiplicity=self.options['multiplicity'],
                    FORCE=self.options['FORCE']
                    )
        else:
            pes1 = PES.from_options(
                    lot=lot,multiplicity=self.options['states'][0][0],
                    ad_idx=self.options['states'][0][1],
                    FORCE=self.['FORCE']
                    )
            pes2 = PES.from_options(
                    lot=lot,
                    multiplicity=self.options['states'][1][0],
                    ad_idx=self.options['states'][1][1],
                    FORCE=self.['FORCE']
                    )
            pes = pes_class.from_options(PES1=pes1,PES2=pes2,lot=lot)

        # Molecule
        printcool("Building the reactant object")
        Form_Hessian = True if self.options['optimizer']=='eigenvector_follow' else False
        reactant = Molecule.from_options(
                fnm=self.options['xyzfile1'],
                PES=pes,
                coordinate_type=self.options['coordinate_type'],
                Form_Hessian=Form_Hessian
                )

        if self.options['GSM_type']=='DE-GSM':
            printcool("Building the product object")
            product = Molecule.from_options(
                    fnm=self.options['xyzfile2'],
                    PES=pes,
                    coordinate_type=self.options['coordinate_type'],
                    Form_Hessian=Form_Hessian
                    )
       
        # optimizer
        printcool("Building the Optimizer object")
        opt_class = getattr(sys.modules[__name__], options['optimizer'])
        optimizer = opt_class.from_options(print_level=self.options['opt_print_level'])

        # GSM
        printcool("Building the GSM object")
        gsm_class = getattr(sys.modules[__name__], options['GSM_type'])
        if GSM_type=="DE_GSM":
            self.gsm = gsm_class.from_options(
                    reactant=reactant,
                    product=product,
                    nnodes=self.options['num_nodes'],
                    CONV_TOL=self.options['CONV_TOL'],
                    ADD_NODE_TOL=self.options['ADD_NODE_TOL'],
                    growth_direction=self.options['growth_direction'],
                    product_geom_fixed=self.options['product_geom_fixed'],
                    optimizer=optimizer,
                    print_level=self.options['gsm_print_level'],
                    )
        else:
            self.gsm = gsm_class.from_options(
                    reactant=reactant,
                    nnodes=self.options['num_nodes'],
                    DQMAG_MAX=self.options['DQMAG_MAX'],
                    BDIST_RATIO=self.options['BDIST_RATIO'],
                    CONV_TOL=self.options['CONV_TOL'],
                    ADD_NODE_TOL=self.options['ADD_NODE_TOL'],
                    optimizer=optimizer,
                    print_level=self.options['gsm_print_level'],
                    driving_coords=self.options['driving_coordinates']
                    )


    def go_gsm(self,max_iters=50,opt_steps=3,rtype=2):
        self.gsm.go_gsm(max_iters=max_iters,opt_steps=opt_steps,rtype=rtype)
        self.post_processing()

    def post_processing(self):
        plot(fx = gsm.energies,x=range(len(gsm.energies)),title=self.gsm.ID,color='b')


#inpfileq = {
#               # LOT
#              'states': [(1,0)],
#              'job_data' : None,
#              'xyzfile' : 'scratch/initial0001.xyz',
#
#              # PES 
#              'pes_type': 'normal', # 'normal', 'penalty', 'average'
#              'adiabatic_index': 0,
#              'multiplicity': 1,
#              'FORCE': None,
#              
#              # Molecule
#              'coordinate_type': 'TRIC',
#
#              # Optimizer
#              'optimizer': 'eigenvector_follow', # L-BFGS, CG
#              'linesearch' 'NoLineSearch', # backtrack
#              'opt_print_level': 1 ,
#
#              # GSM
#              'gsm_type': 'DE-GSM', # SE-GSM, SE-Cross
#              'nnodes' : 9,
#              'driving_coordinates': None,
#              'rp_type':'Exact_TS' # Climb, Op_only
#              'DQMAG_MAX': 0.4,
#              'gsm_print_level': 1,
#               'CONV_TOL': 0.0005,
#
#              }
#