import options
import numpy as np
import os
import pybel as pb
import dlc as ico
from copy import deepcopy
import StringIO

global DQMAG_SSM_SCALE
DQMAG_SSM_SCALE=1.5
global DQMAG_SSM_MAX
DQMAG_SSM_MAX=0.8
global DQMAG_SSM_MIN
DQMAG_SSM_MIN=0.2

class Base_Method(object):
    
    @staticmethod
    def default_options():
        if hasattr(Base_Method, '_default_options'): return Base_Method._default_options.copy()

        opt = options.Options() 
        
        opt.add_option(
            key='ICoord1',
            required=True,
            allowed_types=[ico.DLC],
            doc='')

        opt.add_option(
            key='ICoord2',
            required=False,
            allowed_types=[ico.DLC],
            doc='')

        opt.add_option(
            key='nnodes',
            required=False,
            value=1,
            allowed_types=[int],
            doc='number of string nodes')
        
        opt.add_option(
            key='isSSM',
            required=False,
            value=False,
            allowed_types=[bool],
            doc='specify SSM or DSM')

        opt.add_option(
            key='isomers',
            required=False,
            value=[],
            allowed_types=[list],
            doc='Provide a list of tuples to select coordinates to modify atoms\
                 indexed at 1')

        opt.add_option(
            key='isMAP_SE',
            required=False,
            value=False,
            allowed_types=[bool],
            doc='specify isMAP_SE')

        opt.add_option(
            key='nconstraints',
            required=False,
            value=0,
            allowed_types=[int])

        opt.add_option(
            key='OPTTHRESH',
            value=0.001,
            required=False,
            allowed_types=[float],
            doc='Convergence threshold')


        Base_Method._default_options = opt
        return Base_Method._default_options.copy()


    @staticmethod
    def from_options(**kwargs):
        return Base_Method(Base_Method.default_options().set_values(kwargs))

    def __init__(
            self,
            options,
            ):
        """ Constructor """
        self.options = options

        # Cache some useful attributes

        #TODO What is optCG Ask Paul
        self.optCG = False
        self.isTSnode =False
        self.nnodes = self.options['nnodes']
        self.icoords = [0]*self.nnodes
        self.icoords[0] = self.options['ICoord1']
        if self.nnodes>1:
            self.icoords[-1] = self.options['ICoord2']
        tmp=self.options['ICoord1']
        self.nn = 2
        self.nR = 1
        self.nP = 1        
        self.isSSM = self.options['isSSM']
        self.isMAP_SE = self.options['isMAP_SE']
        self.active = [False] * self.nnodes
        self.active[0] = True
        self.active[-1] = False
        self.isomers = self.options['isomers']
        #self.isomer_init()
        self.nconstraints = self.options['nconstraints']
        self.OPTTHRESH = self.options['OPTTHRESH']

    def optimize(self,n=0,nsteps=100,nconstraints=0):
        xyzfile=os.getcwd()+"/xyzfile.xyz"
        output_format = 'xyz'
        obconversion = ob.OBConversion()
        obconversion.SetOutFormat(output_format)
        opt_molecules=[]
        opt_molecules.append(obconversion.WriteString(self.icoords[n].mol.OBMol))
        self.icoords[n].V0 = self.icoords[n].PES.get_energy(self.icoords[n].geom)
        self.icoords[n].energy=0
        grmss = []
        steps = []
        energies=[]
        Es =[]
        self.icoords[n].do_bfgs=False # gets reset after each step
        self.icoords[n].buf = StringIO.StringIO()
    
        print "Initial energy is %1.4f\n" % self.icoords[n].V0
        self.icoords[n].buf.write("\n Writing convergence:")
    
        for step in range(nsteps):
            if self.icoords[n].print_level==1:
                print("\nOpt step: %i" %(step+1)),
            self.icoords[n].buf.write("\nOpt step: %d" %(step+1))
    
            # => Opt step <= #
            smag =self.icoords[n].opt_step(nconstraints)
            grmss.append(self.icoords[n].gradrms)
            steps.append(smag)
            energies.append(self.icoords[n].energy)
            opt_molecules.append(obconversion.WriteString(self.icoords[n].mol.OBMol))
    
            #write convergence
            largeXyzFile =pb.Outputfile("xyz",xyzfile,overwrite=True)
            for mol in opt_molecules:
                largeXyzFile.write(pb.readstring("xyz",mol))
            with open(xyzfile,'r+') as f:
                content  =f.read()
                f.seek(0,0)
                f.write("[Molden Format]\n[Geometries] (XYZ)\n"+content)
            with open(xyzfile, "a") as f:
                f.write("[GEOCONV]\n")
                f.write("energy\n")
                for energy in energies:
                    f.write('{}\n'.format(energy))
                f.write("max-force\n")
                for grms in grmss:
                    f.write('{}\n'.format(grms))
                f.write("max-step\n")
                for step in steps:
                    f.write('{}\n'.format(step))
    
            if self.icoords[n].gradrms<self.OPTTHRESH:
                break
        print(self.icoords[n].buf.getvalue())
        print "Final energy is %2.5f" % (self.icoords[n].V0 + self.icoords[n].energy)
        return smag

if __name__ == '__main__':
    if 1:
        from pytc import *
        from pes import *
        from dlc import *

        filepath="tests/stretched_fluoroethene.xyz"
        nocc=11
        nactive=2
        lot1=PyTC.from_options(states=[(1,0)],nocc=nocc,nactive=nactive,basis='6-31gs')
        #lot1.cas_from_file(filepath)
        pes = PES.from_options(lot=lot1,ad_idx=0,multiplicity=1)
        mol1=pb.readfile("xyz",filepath).next()
        ic1=DLC.from_options(mol=mol1,PES=pes)
        opt = Base_Method.from_options(ICoord1=ic1)
        ic1.draw()
