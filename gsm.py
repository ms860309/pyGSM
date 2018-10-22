import numpy as np
import options
import os
from base_gsm import *

class GSM(BaseGSM):

    def starting_string(self):
        #dq
        #add_node()
        #add_node()
        return

    def de_gsm(self):
        #grow string
        #for i in range(max_iters)
        #grow_node if okay
        #optimize string
        #find TS
        return

if __name__ == '__main__':
    from icoord import *
    from qchem import *
    import manage_xyz
    filepath="tests/fluoroethene.xyz"
    filepath2="tests/stretched_fluoroethene.xyz"

    # LOT object
#    nocc=23
#    nactive=2
#    lot=PyTC.from_options(calc_states=[(0,0)],filepath=filepath,nocc=nocc,nactive=nactive,basis='6-31gs')
    #lot.cas_from_geom()


    mol=pb.readfile("xyz",filepath).next()
    mol2=pb.readfile("xyz",filepath2).next()
    geom = manage_xyz.read_xyz(filepath,scale=1)
    geom2 = manage_xyz.read_xyz(filepath2,scale=1)
    lot=QChem.from_options(E_states=[(1,0)],geom=geom,basis='6-31g(d)',functional='B3LYP')
    lot2=QChem.from_options(E_states=[(1,0)],geom=geom,basis='6-31g(d)',functional='B3LYP')

    print "\n IC1 \n\n"
    ic1=ICoord.from_options(mol=mol,lot=lot)
    print "\n IC2 \n\n"
    ic2=ICoord.from_options(mol=mol2,lot=lot2)

    print "\n Starting GSM \n\n"
    gsm=GSM.from_options(ICoord1=ic1,ICoord2=ic2,nnodes=9)
    gsm.add_node(0,1,8)
    
    print '\n\n ############ STARTING GSM 2 ############# \n\n'
    gsm2 = GSM.from_options(ICoord1=ic1,nnodes=9,isomers=[('torsions',3,1,2,5,90.)],isSSM=True) 
    gsm2.add_node_SSM(0,1)
