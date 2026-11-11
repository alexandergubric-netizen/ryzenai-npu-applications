"""Offline retrieval evaluation. The fixtures are authored examples, not a reference corpus."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.storage import Store
from core.file_hub import FileHub
from core.knowledge import Knowledge
from core.knowledge_chat import format_hits

# Fixed before running: >=90% positive top-1 per area, all citations exact,
# all four unsupported questions per area must abstain.
CASES={
"coding":[
("recursion","Recursion terminates when execution reaches a base case.","What terminates recursion?","When does a base case stop execution?"),
("queue","A FIFO queue removes the oldest element first.","Which element leaves a FIFO queue first?","What removes the oldest element?"),
("stack","A LIFO stack pops the most recently pushed item.","Which item does a LIFO stack pop?","What stores the most recently pushed item?"),
("mutex","A mutex grants exclusive access to a critical section.","What grants exclusive access?","How is a critical section protected?"),
("hashing","A hash table maps a key to a bucket.","Where does a hash table map a key?","What maps keys to a bucket?"),
("transactions","A rollback discards uncommitted transaction changes.","What does rollback discard?","How are uncommitted changes discarded?"),
("binary","Binary search halves the remaining sorted range at each comparison.","What search halves a sorted range?","How does each comparison reduce the remaining range?"),
("parser","A parser converts tokens into a syntax tree.","What converts tokens into a syntax tree?","What does a parser produce?")],
"biology":[
("osmosis","Osmosis moves water across a selectively permeable membrane.","What moves water across a selectively permeable membrane?","What moves during osmosis?"),
("ribosome","The ribosome translates messenger RNA into a protein.","Where is messenger RNA translated?","What does the ribosome produce?"),
("mitosis","Mitosis separates duplicated chromosomes into two nuclei.","What separates duplicated chromosomes?","How many nuclei result from mitosis?"),
("chlorophyll","Chlorophyll absorbs light for photosynthesis.","Which pigment absorbs light?","What does chlorophyll supply for photosynthesis?"),
("xylem","Xylem transports water and mineral ions from roots.","What transports mineral ions from roots?","What does xylem carry?"),
("antibody","An antibody binds a specific antigen.","What binds a specific antigen?","What does an antibody recognize?"),
("enzyme","An enzyme lowers the activation energy of a reaction.","What lowers activation energy?","How does an enzyme assist a reaction?"),
("meiosis","Meiosis produces haploid cells from a diploid precursor.","What produces haploid cells?","What type of precursor enters meiosis?")],
"chemistry":[
("catalyst","A catalyst speeds a reaction and is regenerated overall.","What speeds a reaction and is regenerated?","What happens to a catalyst overall?"),
("buffer","A buffer resists changes in pH after small additions of acid.","What resists changes in pH?","How does a buffer respond to small additions of acid?"),
("isotope","Isotopes have equal proton counts but different neutron counts.","How do isotopes differ?","Which particles have different neutron counts but equal proton counts?"),
("covalent","A covalent bond shares electron pairs between atoms.","What bond shares electron pairs?","How are atoms joined in a covalent bond?"),
("oxidation","Oxidation is the loss of electrons.","Which process is the loss of electrons?","What is lost during oxidation?"),
("solvent","A solvent dissolves a solute to form a solution.","What dissolves a solute?","What does a solvent form?"),
("titration","Titration measures concentration using a reagent of known strength.","What measures concentration using a known reagent?","What is determined by titration?"),
("distillation","Distillation separates liquids using differences in boiling point.","What separates liquids by boiling point?","What property is used in distillation?")],
"physics":[
("inertia","Inertia is the tendency to resist a change in velocity.","What tendency resists a change in velocity?","What is inertia?"),
("momentum","Linear momentum equals mass times velocity.","What equals mass times velocity?","How is linear momentum calculated?"),
("frequency","Frequency counts cycles per second and is measured in hertz.","What counts cycles per second?","Which quantity is measured in hertz?"),
("ohm","Ohm's law gives voltage as current multiplied by resistance.","What law relates voltage and resistance?","What is current multiplied by resistance?"),
("buoyancy","Buoyancy equals the weight of displaced fluid.","What equals the weight of displaced fluid?","How is buoyancy determined?"),
("refraction","Refraction changes the direction of light at a boundary between media.","What changes light direction at a boundary?","Where does refraction occur?"),
("entropy","Entropy measures the dispersal of energy.","Which quantity measures dispersal of energy?","What does entropy measure?"),
("torque","Torque equals force times perpendicular lever arm.","What equals force times perpendicular lever arm?","How is torque computed?")],
"mathematics":[
("median","The median is the middle value in an ordered list of odd length.","What is the middle value of an ordered list?","How is the median found for odd length?"),
("derivative","A derivative gives the instantaneous rate of change.","What gives an instantaneous rate of change?","What does a derivative describe?"),
("hypotenuse","The hypotenuse lies opposite the right angle of a triangle.","Which side lies opposite the right angle?","Where is the hypotenuse in a triangle?"),
("prime","A prime integer has exactly two positive divisors.","What integer has exactly two positive divisors?","How many divisors define a prime?"),
("variance","Variance is the mean squared deviation from the mean.","What is mean squared deviation?","How is variance defined?"),
("determinant","The absolute determinant is the volume scale factor of a linear transformation.","What gives the volume scale factor?","What does the absolute determinant measure?"),
("bijection","A bijection is both injective and surjective.","Which mapping is both injective and surjective?","What properties define a bijection?"),
("logarithm","A logarithm returns the exponent needed for a base to produce a number.","What returns the exponent for a given base?","What does a logarithm compute?")]}
UNKNOWN={
"coding":["Who invented Prolog?","When was COBOL standardized?","Explain monads.","Describe garbage collection."],
"biology":["What is telomerase?","Where are prions found?","Describe phototropism.","Explain genetic drift."],
"chemistry":["What is Avogadro's constant?","Describe chromatography.","Which salts sublime?","Explain orbital hybridization."],
"physics":["Who discovered pulsars?","Describe gravitational lensing.","Explain superconductivity.","What are quarks?"],
"mathematics":["Describe Euler's identity.","Explain Zorn's lemma.","What are quaternions?","Who proved Fermat's theorem?"]}

def main():
    home=Path(tempfile.mkdtemp(prefix="phase4-eval-",dir=ROOT/".test-runs"))
    files=FileHub(home);kb=Knowledge(Store(home),files);out={}
    for area,cases in CASES.items():
        results=[]
        for slug,passage,*_ in cases:
            name=slug+".txt";(files.root("default")/name).write_text(passage,encoding="utf-8")
            kb.add("default",area,[name])
        for slug,passage,*queries in cases:
            expected=slug+".txt"
            for query in queries:
                hits=kb.search("default",area,query,3)
                valid=all(h["excerpt"]==(files.root("default")/h["source"]).read_text(encoding="utf-8")
                    and h["sha256"]==hashlib.sha256(h["excerpt"].encode()).hexdigest()
                    and h["citation"]==i for i,h in enumerate(hits,1))
                results.append({"query":query,"expected":expected,"first":hits[0]["source"] if hits else None,
                    "citations_valid":valid,"correct":bool(hits and hits[0]["source"]==expected),"answer":format_hits(hits)})
        for query in UNKNOWN[area]:
            hits=kb.search("default",area,query)
            results.append({"query":query,"expected":None,"correct":not hits,"citations_valid":not hits,"answer":format_hits(hits)})
        out[area]=results
        print(area,sum(r["correct"] for r in results[:16]),"/16 positive,",sum(r["correct"] for r in results[16:]),"/4 abstentions")
    (home/"results.json").write_text(json.dumps(out,indent=2),encoding="utf-8")
    print(home)
    return all(sum(r["correct"] for r in rows[:16])>=15 and all(r["citations_valid"] for r in rows) and all(r["correct"] for r in rows[16:]) for rows in out.values())
if __name__=="__main__":sys.exit(0 if main() else 1)

