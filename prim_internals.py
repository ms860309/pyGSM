from internalcoordinates import InternalCoordinates,AtomContact,MyG
from collections import OrderedDict, defaultdict
import itertools
from copy import deepcopy
import networkx as nx
from _math_utils import *
import options
from slots import *
from units import *
from elements import ElementData
from pkg_resources import parse_version
np.set_printoptions(precision=4,suppress=True)

class PrimitiveInternalCoordinates(InternalCoordinates):

    @staticmethod
    def from_options(**kwargs):
        """ Returns an instance of this class with default options updated from values in kwargs"""
        return PrimitiveInternalCoordinates(PrimitiveInternalCoordinates.default_options().set_values(kwargs))

    def __init__(self,
            options
            ):
        
        super(PrimitiveInternalCoordinates, self).__init__(options)

        # Cache some useful attributes
        self.options = options
        constraints = options['constraints']
        cvals = options['cVals']
        self.atoms = options['atoms']
        extra_kwargs=options['extra_kwargs']

        # initialize 
        self.Internals = []
        self.cPrims = []
        self.cVals = []
        self.Rotators = OrderedDict()
        self.natoms = len(self.atoms)
        self.built_bonds = False

        ## Topology settings  -- CRA 3/2019  A lot of this is leftovers from Lee-Ping's code
        # but maybe useful in the future
        self.top_settings = {'toppbc' : extra_kwargs.get('toppbc', False),
                             'topframe' : extra_kwargs.get('topframe', 0),
                             'Fac' : extra_kwargs.get('Fac', 1.2),
                             'read_bonds' : False,
                             'fragment' : extra_kwargs.get('fragment', False),
                             'radii' : extra_kwargs.get('radii', {})}

        xyz = options['xyz']

        # setup
        self.makePrimitives(xyz,options)

        #exit()
        #self.makeConstraints(xyz, constraints, cvals)

        # Reorder primitives for checking with cc's code in TC.
        # Note that reorderPrimitives() _must_ be updated with each new InternalCoordinate class written.
        self.reorderPrimitives()

    def makePrimitives(self, xyz, options):
        connect=options['connect']
        addcart=options['addcart']
        addtr=options['addtr']
        self.build_topology(xyz)

        # LPW also uses resid from molecule . . . 
        frags = [m.nodes() for m in self.fragments]

        # coordinates in Angstrom
        coords = xyz.flatten()
        # Make a distance matrix mapping atom pairs to interatomic distances
        AtomIterator, dxij = self.distance_matrix(xyz,pbc=False)
        D = {}
        for i, j in zip(AtomIterator, dxij[0]):
            assert i[0] < i[1]
            D[tuple(i)] = j
        dgraph = nx.Graph()
        for i in range(self.natoms):
            dgraph.add_node(i)
        for k, v in D.items():
            dgraph.add_edge(k[0], k[1], weight=v)
        mst = sorted(list(nx.minimum_spanning_edges(dgraph, data=False)))
        # Build a list of noncovalent distances
        noncov = []
        # Connect all non-bonded fragments together
        for edge in mst:
            if edge not in list(self.topology.edges()):
                if connect:
                    print "Adding %s from minimum spanning tree" % str(edge)
                    self.topology.add_edge(edge[0], edge[1])
                    noncov.append(edge)
        if not connect:
            if addcart:
                for i in range(self.natoms):
                    self.add(CartesianX(i, w=1.0))
                    self.add(CartesianY(i, w=1.0))
                    self.add(CartesianZ(i, w=1.0))
            elif addtr:
                for i in frags:
                    if len(i) >= 2:
                        self.add(TranslationX(i, w=np.ones(len(i))/len(i)))
                        self.add(TranslationY(i, w=np.ones(len(i))/len(i)))
                        self.add(TranslationZ(i, w=np.ones(len(i))/len(i)))
                        sel = coords.reshape(-1,3)[i,:] 
                        sel -= np.mean(sel, axis=0)
                        rg = np.sqrt(np.mean(np.sum(sel**2, axis=1)))
                        self.add(RotationA(i, coords, self.Rotators, w=rg))
                        self.add(RotationB(i, coords, self.Rotators, w=rg))
                        self.add(RotationC(i, coords, self.Rotators, w=rg))
                    else:
                        for j in i:
                            self.add(CartesianX(j, w=1.0))
                            self.add(CartesianY(j, w=1.0))
                            self.add(CartesianZ(j, w=1.0))
            else:
                if len(frags)>1:
                    raise RuntimeError("need someway to define the intermolecular interaction")

        # # Build a list of noncovalent distances
        # Add an internal coordinate for all interatomic distances
        for (a, b) in self.topology.edges():
            self.add(Distance(a, b))

        # Add an internal coordinate for all angles
        # This number works best for the iron complex
        LinThre = 0.95
        AngDict = defaultdict(list)
        for b in self.topology.nodes():
            for a in self.topology.neighbors(b):
                for c in self.topology.neighbors(b):
                    if a < c:
                        # if (a, c) in self.topology.edges() or (c, a) in self.topology.edges(): continue
                        Ang = Angle(a, b, c)
                        nnc = (min(a, b), max(a, b)) in noncov
                        nnc += (min(b, c), max(b, c)) in noncov
                        # if nnc >= 2: continue
                        # logger.info("LPW: cosine of angle", a, b, c, "is", np.abs(np.cos(Ang.value(coords))))
                        if np.abs(np.cos(Ang.value(coords))) < LinThre:
                            self.add(Angle(a, b, c))
                            AngDict[b].append(Ang)
                        elif connect or not addcart:
                            # logger.info("Adding linear angle")
                            # Add linear angle IC's
                            # LPW 2019-02-16: Linear angle ICs work well for "very" linear angles in selfs (e.g. HCCCN)
                            # but do not work well for "almost" linear angles in noncovalent systems (e.g. H2O6).
                            # Bringing back old code to use "translations" for the latter case, but should be investigated
                            # more deeply in the future.
                            if nnc == 0:
                                self.add(LinearAngle(a, b, c, 0))
                                self.add(LinearAngle(a, b, c, 1))
                            else:
                                # Unit vector connecting atoms a and c
                                nac = xyz[c] - xyz[a]
                                nac /= np.linalg.norm(nac)
                                # Dot products of this vector with the Cartesian axes
                                dots = [np.abs(np.dot(ei, nac)) for ei in np.eye(3)]
                                # Functions for adding Cartesian coordinate
                                # carts = [CartesianX, CartesianY, CartesianZ]
                                print("warning, adding translation, did you mean this?")
                                trans = [TranslationX, TranslationY, TranslationZ]
                                w = np.array([-1.0, 2.0, -1.0])
                                # Add two of the most perpendicular Cartesian coordinates
                                for i in np.argsort(dots)[:2]:
                                    self.add(trans[i]([a, b, c], w=w))
                            
        for b in self.topology.nodes():
            for a in self.topology.neighbors(b):
                for c in self.topology.neighbors(b):
                    for d in self.topology.neighbors(b):
                        if a < c < d:
                            nnc = (min(a, b), max(a, b)) in noncov
                            nnc += (min(b, c), max(b, c)) in noncov
                            nnc += (min(b, d), max(b, d)) in noncov
                            # if nnc >= 1: continue
                            for i, j, k in sorted(list(itertools.permutations([a, c, d], 3))):
                                Ang1 = Angle(b,i,j)
                                Ang2 = Angle(i,j,k)
                                if np.abs(np.cos(Ang1.value(coords))) > LinThre: continue
                                if np.abs(np.cos(Ang2.value(coords))) > LinThre: continue
                                if np.abs(np.dot(Ang1.normal_vector(coords), Ang2.normal_vector(coords))) > LinThre:
                                    self.delete(Angle(i, b, j))
                                    self.add(OutOfPlane(b, i, j, k))
                                    break
                                
        # Find groups of atoms that are in straight lines
        atom_lines = [list(i) for i in self.topology.edges()]
        while True:
            # For a line of two atoms (one bond):
            # AB-AC
            # AX-AY
            # i.e. AB is the first one, AC is the second one
            # AX is the second-to-last one, AY is the last one
            # AB-AC-...-AX-AY
            # AB-(AC, AX)-AY
            atom_lines0 = deepcopy(atom_lines)
            for aline in atom_lines:
                # Imagine a line of atoms going like ab-ac-ax-ay.
                # Our job is to extend the line until there are no more
                ab = aline[0]
                ay = aline[-1]
                for aa in self.topology.neighbors(ab):
                    if aa not in aline:
                        # If the angle that AA makes with AB and ALL other atoms AC in the line are linear:
                        # Add AA to the front of the list
                        if all([np.abs(np.cos(Angle(aa, ab, ac).value(coords))) > LinThre for ac in aline[1:] if ac != ab]):
                            aline.insert(0, aa)
                for az in self.topology.neighbors(ay):
                    if az not in aline:
                        if all([np.abs(np.cos(Angle(ax, ay, az).value(coords))) > LinThre for ax in aline[:-1] if ax != ay]):
                            aline.append(az)
            if atom_lines == atom_lines0: break
        atom_lines_uniq = []
        for i in atom_lines:    # 
            if tuple(i) not in set(atom_lines_uniq):
                atom_lines_uniq.append(tuple(i))
        lthree = [l for l in atom_lines_uniq if len(l) > 2]
        # TODO: Perhaps should reduce the times this is printed out in reaction paths
        # if len(lthree) > 0:
        #     print "Lines of three or more atoms:", ', '.join(['-'.join(["%i" % (i+1) for i in l]) for l in lthree])

        # Normal dihedral code
        for aline in atom_lines_uniq:
            # Go over ALL pairs of atoms in a line
            for (b, c) in itertools.combinations(aline, 2):
                if b > c: (b, c) = (c, b)
                # Go over all neighbors of b
                for a in self.topology.neighbors(b):
                    # Go over all neighbors of c
                    for d in self.topology.neighbors(c):
                        # Make sure the end-atoms are not in the line and not the same as each other
                        if a not in aline and d not in aline and a != d:
                            nnc = (min(a, b), max(a, b)) in noncov
                            nnc += (min(b, c), max(b, c)) in noncov
                            nnc += (min(c, d), max(c, d)) in noncov
                            # print aline, a, b, c, d
                            Ang1 = Angle(a,b,c)
                            Ang2 = Angle(b,c,d)
                            # Eliminate dihedrals containing angles that are almost linear
                            # (should be eliminated already)
                            if np.abs(np.cos(Ang1.value(coords))) > LinThre: continue
                            if np.abs(np.cos(Ang2.value(coords))) > LinThre: continue
                            self.add(Dihedral(a, b, c, d))
            

    def makeConstraints(self, xyz, constraints, cvals=None):
        # Add the list of constraints. 
        xyz = xyz.flatten()
        if cvals is None and constraints is not None:
            cvals=[]
            # If coordinates are provided instead of a constraint value, 
            # then calculate the constraint value from the positions.
            # If both are provided, then the coordinates are ignored.
            for c in constraints:
                cvals.append(c.value(xyz))
            if len(constraints) != len(cvals):
                raise RuntimeError("List of constraints should be same length as constraint values")
            for cons, cval in zip(constraints, cvals):
                self.addConstraint(cons, cval, xyz)

    def __repr__(self):
        lines = ["Internal coordinate system (atoms numbered from 1):"]
        typedict = OrderedDict()
        for Internal in self.Internals:
            lines.append(Internal.__repr__())
            if str(type(Internal)) not in typedict:
                typedict[str(type(Internal))] = 1
            else:
                typedict[str(type(Internal))] += 1
        if len(lines) > 200:
            # Print only summary if too many
            lines = []
        for k, v in typedict.items():
            lines.append("%s : %i" % (k, v))
        return '\n'.join(lines)

    def __eq__(self, other):
        answer = True
        for i in self.Internals:
            if i not in other.Internals:
                answer = False
        for i in other.Internals:
            if i not in self.Internals:
                answer = False
        return answer

    def __ne__(self, other):
        return not self.__eq__(other)

    def update(self, other):
        Changed = False
        for i in self.Internals:
            if i not in other.Internals:
                if hasattr(i, 'inactive'):
                    i.inactive += 1
                else:
                    i.inactive = 0
                if i.inactive == 1:
                    logger.info("Deleting:", i)
                    self.Internals.remove(i)
                    Changed = True
            else:
                i.inactive = 0
        for i in other.Internals:
            if i not in self.Internals:
                logger.info("Adding:  ", i)
                self.Internals.append(i)
                Changed = True
        return Changed

    def join(self, other):
        Changed = False
        for i in other.Internals:
            if i not in self.Internals:
                #logger.info("Adding:  ", i)
                print("Adding ",i)
                self.Internals.append(i)
                Changed = True
        return Changed

    def repr_diff(self, other):
        alines = ["-- Added: --"]
        for i in other.Internals:
            if i not in self.Internals:
                alines.append(i.__repr__())
        dlines = ["-- Deleted: --"]
        for i in self.Internals:
            if i not in other.Internals:
                dlines.append(i.__repr__())
        output = []
        if len(alines) > 1:
            output += alines
        if len(dlines) > 1:
            output += dlines
        return '\n'.join(output)

    def resetRotations(self, xyz):
        for Internal in self.Internals:
            if type(Internal) is LinearAngle:
                Internal.reset(xyz)
        for rot in self.Rotators.values():
            rot.reset(xyz)

    def largeRots(self):
        for Internal in self.Internals:
            if type(Internal) is LinearAngle:
                if Internal.stored_dot2 > 0.75:
                    # Linear angle is almost parallel to reference axis
                    return True
            if type(Internal) in [RotationA, RotationB, RotationC]:
                if Internal in self.cPrims:
                    continue
                if Internal.Rotator.stored_norm > 0.9*np.pi:
                    # Molecule has rotated by almost pi
                    return True
                if Internal.Rotator.stored_dot2 > 0.9:
                    # Linear molecule is almost parallel to reference axis
                    return True
        return False

    def calculate(self, xyz):
        answer = []
        for Internal in self.Internals:
            answer.append(Internal.value(xyz))
        return np.array(answer)

    def calculateDegrees(self, xyz):
        answer = []
        for Internal in self.Internals:
            value = Internal.value(xyz)
            if Internal.isAngular:
                value *= 180/np.pi
            answer.append(value)
        return np.array(answer)

    def getRotatorNorms(self):
        rots = []
        for Internal in self.Internals:
            if type(Internal) in [RotationA]:
                rots.append(Internal.Rotator.stored_norm)
        return rots

    def getRotatorDots(self):
        dots = []
        for Internal in self.Internals:
            if type(Internal) in [RotationA]:
                dots.append(Internal.Rotator.stored_dot2)
        return dots

    def printRotations(self, xyz):
        rotNorms = self.getRotatorNorms()
        if len(rotNorms) > 0:
            logger.info("Rotator Norms: ", " ".join(["% .4f" % i for i in rotNorms]))
        rotDots = self.getRotatorDots()
        if len(rotDots) > 0 and np.max(rotDots) > 1e-5:
            logger.info("Rotator Dots : ", " ".join(["% .4f" % i for i in rotDots]))
        linAngs = [ic.value(xyz) for ic in self.Internals if type(ic) is LinearAngle]
        if len(linAngs) > 0:
            logger.info("Linear Angles: ", " ".join(["% .4f" % i for i in linAngs]))

    def derivatives(self, xyz):
        self.calculate(xyz)
        answer = []
        for Internal in self.Internals:
            answer.append(Internal.derivative(xyz))
        # This array has dimensions:
        # 1) Number of internal coordinates
        # 2) Number of atoms
        # 3) 3
        return np.array(answer)

    def calcDiff(self, coord1, coord2):
        """ Calculate difference in internal coordinates, accounting for changes in 2*pi of angles. """
        Q1 = self.calculate(coord1)
        Q2 = self.calculate(coord2)
        PMDiff = (Q1-Q2)
        for k in range(len(PMDiff)):
            if self.Internals[k].isPeriodic:
                Plus2Pi = PMDiff[k] + 2*np.pi
                Minus2Pi = PMDiff[k] - 2*np.pi
                if np.abs(PMDiff[k]) > np.abs(Plus2Pi):
                    PMDiff[k] = Plus2Pi
                if np.abs(PMDiff[k]) > np.abs(Minus2Pi):
                    PMDiff[k] = Minus2Pi
        return PMDiff

    def GInverse(self, xyz):
        return self.GInverse_SVD(xyz)

    def add(self, dof):
        if dof not in self.Internals:
            self.Internals.append(dof)

    def delete(self, dof):
        for ii in range(len(self.Internals))[::-1]:
            if dof == self.Internals[ii]:
                del self.Internals[ii]

    def addConstraint(self, cPrim, cVal=None, xyz=None):
        if cVal is None and xyz is None:
            raise RuntimeError('Please provide either cval or xyz')
        if cVal is None:
            # If coordinates are provided instead of a constraint value, 
            # then calculate the constraint value from the positions.
            # If both are provided, then the coordinates are ignored.
            cVal = cPrim.value(xyz)
            print cVal
        if cPrim in self.cPrims:
            iPrim = self.cPrims.index(cPrim)
            if np.abs(cVal - self.cVals[iPrim]) > 1e-6:
                logger.info("Updating constraint value to %.4e" % cVal)
            self.cVals[iPrim] = cVal
        else:
            if cPrim not in self.Internals:
                self.Internals.append(cPrim)
            self.cPrims.append(cPrim)
            self.cVals.append(cVal)

    def reorderPrimitives(self):
        # Reorder primitives to be in line with cc's code
        newPrims = []
        for cPrim in self.cPrims:
            newPrims.append(cPrim)
        for typ in [Distance, Angle, LinearAngle, MultiAngle, OutOfPlane, Dihedral, MultiDihedral, CartesianX, CartesianY, CartesianZ, TranslationX, TranslationY, TranslationZ, RotationA, RotationB, RotationC]:
            for p in self.Internals:
                if type(p) is typ and p not in self.cPrims:
                    newPrims.append(p)
        if len(newPrims) != len(self.Internals):
            raise RuntimeError("Not all internal coordinates have been accounted for. You may need to add something to reorderPrimitives()")
        self.Internals = newPrims

    def getConstraints_from(self, other):
        if other.haveConstraints():
            for cPrim, cVal in zip(other.cPrims, other.cVals):
                self.addConstraint(cPrim, cVal)

    def haveConstraints(self):
        return len(self.cPrims) > 0

    def getConstraintViolation(self, xyz):
        nc = len(self.cPrims)
        maxdiff = 0.0
        for ic, c in enumerate(self.cPrims):
            w = c.w if type(c) in [RotationA, RotationB, RotationC] else 1.0
            current = c.value(xyz)/w
            reference = self.cVals[ic]/w
            diff = (current - reference)
            if c.isPeriodic:
                if np.abs(diff-2*np.pi) < np.abs(diff):
                    diff -= 2*np.pi
                if np.abs(diff+2*np.pi) < np.abs(diff):
                    diff += 2*np.pi
            if type(c) in [TranslationX, TranslationY, TranslationZ, CartesianX, CartesianY, CartesianZ, Distance]:
                factor = 1.
            elif c.isAngular:
                factor = 180.0/np.pi
            if np.abs(diff*factor) > maxdiff:
                maxdiff = np.abs(diff*factor)
        return maxdiff
    
    def printConstraints(self, xyz, thre=1e-5):
        nc = len(self.cPrims)
        out_lines = []
        header = "Constraint                         Current      Target       Diff.\n"
        for ic, c in enumerate(self.cPrims):
            w = c.w if type(c) in [RotationA, RotationB, RotationC] else 1.0
            current = c.value(xyz)/w
            reference = self.cVals[ic]/w
            diff = (current - reference)
            if c.isPeriodic:
                if np.abs(diff-2*np.pi) < np.abs(diff):
                    diff -= 2*np.pi
                if np.abs(diff+2*np.pi) < np.abs(diff):
                    diff += 2*np.pi
            if type(c) in [TranslationX, TranslationY, TranslationZ, CartesianX, CartesianY, CartesianZ, Distance]:
                factor = 1.
            elif c.isAngular:
                factor = 180.0/np.pi
            #if np.abs(diff*factor) > thre:
            out_lines.append("%-30s  % 10.5f  % 10.5f  % 10.5f\n" % (str(c), current*factor, reference*factor, diff*factor))
        if len(out_lines) > 0:
            logger.info(header)
            logger.info('\n'.join(out_lines))
            # if type(c) in [RotationA, RotationB, RotationC]:
            #     print c, c.value(xyz)
            #     logArray(c.x0)

    def getConstraintTargetVals(self):
        nc = len(self.cPrims)
        cNames = []
        cVals = []
        for ic, c in enumerate(self.cPrims):
            w = c.w if type(c) in [RotationA, RotationB, RotationC] else 1.0
            reference = self.cVals[ic]/w
            if type(c) in [TranslationX, TranslationY, TranslationZ, CartesianX, CartesianY, CartesianZ, Distance]:
                factor = 1.
            elif c.isAngular:
                factor = 180.0/np.pi
            cNames.append(str(c))
            cVals.append(reference*factor)
        return(cNames, cVals)

    def guess_hessian(self, coords):
        """
        Build a guess Hessian that roughly follows Schlegel's guidelines. 
        """
        xyzs = coords.reshape(-1,3)
        Hdiag = []
        def covalent(a, b):
            r = np.linalg.norm(xyzs[a]-xyzs[b])
            rcov = self.atoms[a].covalent_radius + self.atoms[b].covalent_radius
            return r/rcov < 1.2
        
        for ic in self.Internals:
            if type(ic) is Distance:
                r = np.linalg.norm(xyzs[ic.a]-xyzs[ic.b]) 
                elem1 = min(self.atoms[ic.a].atomic_num,self.atoms[ic.b].atomic_num)
                elem2 = max(self.atoms[ic.a].atomic_num,self.atoms[ic.b].atomic_num)
                A = 1.734
                if elem1 < 3:
                    if elem2 < 3:
                        B = -0.244
                    elif elem2 < 11:
                        B = 0.352
                    else:
                        B = 0.660
                elif elem1 < 11:
                    if elem2 < 11:
                        B = 1.085
                    else:
                        B = 1.522
                else:
                    B = 2.068
                if covalent(ic.a, ic.b):
                    Hdiag.append(A/(r-B)**3)
                else:
                    Hdiag.append(0.1)
            elif type(ic) in [Angle, LinearAngle, MultiAngle]:
                if type(ic) in [Angle, LinearAngle]:
                    a = ic.a
                    c = ic.c
                else:
                    a = ic.a[-1]
                    c = ic.c[0]
                if min(self.atoms[a].atomic_num,
                        self.atoms[ic.b].atomic_num,
                        self.atoms[c].atomic_num) < 3:
                    A = 0.160
                else:
                    A = 0.250
                if covalent(a, ic.b) and covalent(ic.b, c):
                    Hdiag.append(A)
                else:
                    Hdiag.append(0.1)
            elif type(ic) in [Dihedral, MultiDihedral]:
                r = np.linalg.norm(xyzs[ic.b]-xyzs[ic.c])
                rcov = self.atoms[ic.b].covalent_radius + self.atoms[ic.c].covalent_radius
                # Hdiag.append(0.1)
                Hdiag.append(0.023)
            elif type(ic) is OutOfPlane:
                r1 = xyzs[ic.b]-xyzs[ic.a]
                r2 = xyzs[ic.c]-xyzs[ic.a]
                r3 = xyzs[ic.d]-xyzs[ic.a]
                d = 1 - np.abs(np.dot(r1,np.cross(r2,r3))/np.linalg.norm(r1)/np.linalg.norm(r2)/np.linalg.norm(r3))
                # Hdiag.append(0.1)
                if covalent(ic.a, ic.b) and covalent(ic.a, ic.c) and covalent(ic.a, ic.d):
                    Hdiag.append(0.045)
                else:
                    Hdiag.append(0.023)
            elif type(ic) in [CartesianX, CartesianY, CartesianZ]:
                Hdiag.append(0.05)
            elif type(ic) in [TranslationX, TranslationY, TranslationZ]:
                Hdiag.append(0.05)
            elif type(ic) in [RotationA, RotationB, RotationC]:
                Hdiag.append(0.05)
            else:
                raise RuntimeError('Failed to build guess Hessian matrix. Make sure all IC types are supported')
        return np.diag(Hdiag)

    def build_topology(self, xyz, force_bonds=True, **kwargs):
        """
        Create self.topology and self.fragments; these are graph
        representations of the individual molecule fragments
        contained in the Molecule object.

        Parameters
        ----------
        force_bonds : bool
            Build the bonds from interatomic distances.  If the user
            calls build_topology from outside, assume this is the
            default behavior.  If creating a Molecule object using
            __init__, do not force the building of bonds by default
            (only build bonds if not read from file.)
        topframe : int, optional
            Provide the frame number used for reading the bonds.  If
            not provided, this will be taken from the top_settings
            field.  If provided, this will take priority and write
            the value into top_settings.
        """
        # can do an assert for xyz here CRA TODO
        if self.natoms > 100000:
            logger.warning("Warning: Large number of atoms (%i), topology building may take a long time" % self.natoms)

        bonds = self.build_bonds(xyz)

        # Create a NetworkX graph object to hold the bonds.
        G = MyG()
        for i, a_dict in enumerate(self.atoms):
            a = a_dict.name
            G.add_node(i)
            if parse_version(nx.__version__) >= parse_version('2.0'):
                nx.set_node_attributes(G,{i:a}, name='e')
                nx.set_node_attributes(G,{i:xyz[i]}, name='x')
            else:
                nx.set_node_attributes(G,'e',{i:a})
                nx.set_node_attributes(G,'x',{i:xyz[i]})
        for (i, j) in bonds:
            G.add_edge(i, j)

        # The Topology is simply the NetworkX graph object.
        self.topology = G
        self.fragments = [G.subgraph(c).copy() for c in nx.connected_components(G)]
        for g in self.fragments: g.__class__ = MyG
        # Deprecated in networkx 2.2
        # self.fragments = list(nx.connected_component_subgraphs(G))

        # show topology
        #import matplotlib.pyplot as plt
        #plt.plot()
        #nx.draw(m.topology,with_labels=True,font_weight='bold')
        #plt.show()
        #plt.svefig('tmp.png')

        return G

    def build_bonds(self,xyz):
        """ Build the bond connectivity graph. """

        # leftover from LPW code
        sn = self.top_settings['topframe']
        toppbc = self.top_settings['toppbc']
        Fac = self.top_settings['Fac']

        mindist = 1.0 # Any two atoms that are closer than this distance are bonded.
        # Create an atom-wise list of covalent radii.
        # Molecule object can have its own set of radii that overrides the global ones
        R = np.array([self.top_settings['radii'].get(i.symbol, i.covalent_radius) for i in self.atoms])
        # Create a list of 2-tuples corresponding to combinations of atomic indices using a grid algorithm.
        mins = np.min(xyz,axis=0)
        maxs = np.max(xyz,axis=0)
        # Grid size in Angstrom.  This number is optimized for speed in a 15,000 atom system (united atom pentadecane).
        gsz = 6.0
        if hasattr(self, 'boxes'):
            xmin = 0.0
            ymin = 0.0
            zmin = 0.0
            xmax = self.boxes[sn].a
            ymax = self.boxes[sn].b
            zmax = self.boxes[sn].c
            if any([i != 90.0 for i in [self.boxes[sn].alpha, self.boxes[sn].beta, self.boxes[sn].gamma]]):
                logger.warning("Warning: Topology building will not work with broken molecules in nonorthogonal cells.")
                toppbc = False
        else:
            xmin = mins[0]
            ymin = mins[1]
            zmin = mins[2]
            xmax = maxs[0]
            ymax = maxs[1]
            zmax = maxs[2]
            toppbc = False

        xext = xmax-xmin
        yext = ymax-ymin
        zext = zmax-zmin

        if toppbc:
            gszx = xext/int(xext/gsz)
            gszy = yext/int(yext/gsz)
            gszz = zext/int(zext/gsz)
        else:
            gszx = gsz
            gszy = gsz
            gszz = gsz

        # Run algorithm to determine bonds.
        # Decide if we want to use the grid algorithm.
        use_grid = toppbc or (np.min([xext, yext, zext]) > 2.0*gsz)
        if use_grid:
            # Inside the grid algorithm.
            # 1) Determine the left edges of the grid cells.
            # Note that we leave out the rightmost grid cell,
            # because this may cause spurious partitionings.
            xgrd = np.arange(xmin, xmax-gszx, gszx)
            ygrd = np.arange(ymin, ymax-gszy, gszy)
            zgrd = np.arange(zmin, zmax-gszz, gszz)
            # 2) Grid cells are denoted by a three-index tuple.
            gidx = list(itertools.product(range(len(xgrd)), range(len(ygrd)), range(len(zgrd))))
            # 3) Build a dictionary which maps a grid cell to itself plus its neighboring grid cells.
            # Two grid cells are defined to be neighbors if the differences between their x, y, z indices are at most 1.
            gngh = OrderedDict()
            amax = np.array(gidx[-1])
            amin = np.array(gidx[0])
            n27 = np.array(list(itertools.product([-1,0,1],repeat=3)))
            for i in gidx:
                gngh[i] = []
                ai = np.array(i)
                for j in n27:
                    nj = ai+j
                    for k in range(3):
                        mod = amax[k]-amin[k]+1
                        if nj[k] < amin[k]:
                            nj[k] += mod
                        elif nj[k] > amax[k]:
                            nj[k] -= mod
                    gngh[i].append(tuple(nj))
            # 4) Loop over the atoms and assign each to a grid cell.
            # Note: I think this step becomes the bottleneck if we choose very small grid sizes.
            gasn = OrderedDict([(i, []) for i in gidx])
            for i in range(self.natoms):
                xidx = -1
                yidx = -1
                zidx = -1
                for j in xgrd:
                    xi = xyz[i][0]
                    while xi < xmin: xi += xext
                    while xi > xmax: xi -= xext
                    if xi < j: break
                    xidx += 1
                for j in ygrd:
                    yi = xyz[i][1]
                    while yi < ymin: yi += yext
                    while yi > ymax: yi -= yext
                    if yi < j: break
                    yidx += 1
                for j in zgrd:
                    zi = xyz[i][2]
                    while zi < zmin: zi += zext
                    while zi > zmax: zi -= zext
                    if zi < j: break
                    zidx += 1
                gasn[(xidx,yidx,zidx)].append(i)

            # 5) Create list of 2-tuples corresponding to combinations of atomic indices.
            # This is done by looping over pairs of neighboring grid cells and getting Cartesian products of atom indices inside.
            # It may be possible to get a 2x speedup by eliminating forward-reverse pairs (e.g. (5, 4) and (4, 5) and duplicates (5,5).)
            AtomIterator = []
            for i in gasn:
                for j in gngh[i]:
                    apairs = cartesian_product2([gasn[i], gasn[j]])
                    if len(apairs) > 0: AtomIterator.append(apairs[apairs[:,0]>apairs[:,1]])
            AtomIterator = np.ascontiguousarray(np.vstack(AtomIterator))
        else:
            # Create a list of 2-tuples corresponding to combinations of atomic indices.
            # This is much faster than using itertools.combinations.
            AtomIterator = np.ascontiguousarray(np.vstack((np.fromiter(itertools.chain(*[[i]*(self.natoms-i-1) for i in range(self.natoms)]),dtype=np.int32), np.fromiter(itertools.chain(*[range(i+1,self.natoms) for i in range(self.natoms)]),dtype=np.int32))).T)

        # Create a list of thresholds for determining whether a certain interatomic distance is considered to be a bond.
        BT0 = R[AtomIterator[:,0]]
        BT1 = R[AtomIterator[:,1]]
        BondThresh = (BT0+BT1) * Fac
        BondThresh = (BondThresh > mindist) * BondThresh + (BondThresh < mindist) * mindist
        if hasattr(self, 'boxes') and toppbc:
            dxij = AtomContact(xyz, AtomIterator, box=np.array([self.boxes[sn].a, self.boxes[sn].b, self.boxes[sn].c]))
        else:
            dxij = AtomContact(xyz, AtomIterator)

        # Update topology settings with what we learned
        self.top_settings['toppbc'] = toppbc

        # Create a list of atoms that each atom is bonded to.
        atom_bonds = [[] for i in range(self.natoms)]
        bond_bool = dxij < BondThresh
        for i, a in enumerate(bond_bool):
            if not a: continue
            (ii, jj) = AtomIterator[i]
            if ii == jj: continue
            atom_bonds[ii].append(jj)
            atom_bonds[jj].append(ii)
        bondlist = []

        for i, bi in enumerate(atom_bonds):
            for j in bi:
                if i == j: continue
                # Do not add a bond between resids if fragment is set to True.
                #if self.top_settings['fragment'] and 'resid' in self.Data.keys() and self.resid[i] != self.resid[j]:
                #    continue
                elif i < j:
                    bondlist.append((i, j))
                else:
                    bondlist.append((j, i))
        bondlist = sorted(list(set(bondlist)))
        bonds = sorted(list(set(bondlist)))
        self.built_bonds = True

        return bonds

    def distance_matrix(self,xyz, pbc=True):
        """ Obtain distance matrix between all pairs of atoms. """
        AtomIterator = np.ascontiguousarray(np.vstack((np.fromiter(itertools.chain(*[[i]*(self.natoms-i-1) for i in range(self.natoms)]),dtype=np.int32), np.fromiter(itertools.chain(*[range(i+1,self.natoms) for i in range(self.natoms)]),dtype=np.int32))).T)
        drij = []
        if hasattr(self, 'boxes') and pbc:
            drij.append(AtomContact(xyz,AtomIterator,box=np.array([self.boxes[sn].a, self.boxes[sn].b, self.boxes[sn].c])))
        else:
            drij.append(AtomContact(xyz,AtomIterator))
        return AtomIterator, drij

    def distance_displacement(xyz,self):
        """ Obtain distance matrix and displacement vectors between all pairs of atoms. """
        AtomIterator = np.ascontiguousarray(np.vstack((np.fromiter(itertools.chain(*[[i]*(self.natoms-i-1) for i in range(self.natoms)]),dtype=np.int32), np.fromiter(itertools.chain(*[range(i+1,self.natoms) for i in range(self.natoms)]),dtype=np.int32))).T)
        drij = []
        dxij = []
        if hasattr(self, 'boxes') and pbc:
            drij_i, dxij_i = AtomContact(xyz,AtomIterator,box=np.array([self.boxes[sn].a, self.boxes[sn].b, self.boxes[sn].c]),displace=True)
        else:
            drij_i, dxij_i = AtomContact(xyz,AtomIterator,box=None,displace=True)
        drij.append(drij_i)
        dxij.append(dxij_i)
        return AtomIterator, drij, dxij


    # these aren't used 
    def find_angles(self):

        """ Return a list of 3-tuples corresponding to all of the
        angles in the system.  Verified for lysine and tryptophan
        dipeptide when comparing to TINKER's analyze program. """

        if not hasattr(self, 'topology'):
            logger.error("Need to have built a topology to find angles\n")
            raise RuntimeError

        angidx = []
        # Iterate over separate molecules
        for mol in self.fragments:
            # Iterate over atoms in the molecule
            for a2 in list(mol.nodes()):
                # Find all bonded neighbors to this atom
                friends = sorted(list(nx.neighbors(mol, a2)))
                if len(friends) < 2: continue
                # Double loop over bonded neighbors
                for i, a1 in enumerate(friends):
                    for a3 in friends[i+1:]:
                        # Add bonded atoms in the correct order
                        angidx.append((a1, a2, a3))
        return angidx

    # these aren't used 
    def find_dihedrals(self):

        """ Return a list of 4-tuples corresponding to all of the
        dihedral angles in the system.  Verified for alanine and
        tryptophan dipeptide when comparing to TINKER's analyze
        program. """

        if not hasattr(self, 'topology'):
            logger.error("Need to have built a topology to find dihedrals\n")
            raise RuntimeError

        dihidx = []
        # Iterate over separate molecules
        for mol in self.fragments:
            # Iterate over bonds in the molecule
            for edge in list(mol.edges()):
                # Determine correct ordering of atoms (middle atoms are ordered by convention)
                a2 = edge[0] if edge[0] < edge[1] else edge[1]
                a3 = edge[1] if edge[0] < edge[1] else edge[0]
                for a1 in sorted(list(nx.neighbors(mol, a2))):
                    if a1 != a3:
                        for a4 in sorted(list(nx.neighbors(mol, a3))):
                            if a4 != a2 and len({a1, a2, a3, a4}) == 4:
                                dihidx.append((a1, a2, a3, a4))
        return dihidx


if __name__ =='__main__':
    from molecule import Molecule
    filepath='examples/tests/fluoroethene.xyz'
    M = Molecule.from_options(fnm=filepath)
    #print type(M.atoms)

    p = PrimitiveInternalCoordinates.from_options(xyz=M.xyz,atoms=M.atoms) 
    idx = p.find_dihedrals()
    print idx
