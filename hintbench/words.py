"""Embedded 5-letter word catalog for the wordle self-check environment.

Deliberately small and fully visible to the agent: the scored skill is
filtering a visible candidate set with feedback and hints, not vocabulary
recall (construct purity: unobserved rules must be made observable).
"""

ANSWERS: tuple[str, ...] = tuple(
    w
    for w in """
aback abide about above abuse actor acute admit adopt adore after again agent agree
ahead alarm album alert alike alive allow alone along alter among anger angle
angry ankle apart apple apply arena argue arise array aside asset audio audit avoid
awake award aware badly baker basic beach began begin being below bench birth
black blame blank blast blend blind block blood board bonus boost bound brain
brand brave bread break breed brick bride brief bring broad broke brown brush
build burst buyer cable candy carry catch cause chain chair chaos charm chart
chase cheap check chess chief child choir chose cider cigar civil claim class clean clear
clerk click cliff climb clock close cloth cloud coach coast color could count
court cover crack craft crane crash crazy cream crime cross crowd crown curve cycle
daily dance dealt death debut delay depth diary dirty dozen draft drama dream
dress drink drive early earth eight elder elect elite empty enemy enjoy enter
entry equal error event every exact exist extra faith false fancy fault favor
feast fence fever field fifty fight final first flame flash fleet flesh float
floor fluid focus force forth forty forum found frame fresh front frost fruit
fully funny giant given glass globe glory glove grace grain grand grant grape
grass great green greet grief gross group guard guess guest guide happy harsh
heart heavy hello honey honor horse hotel house human hurry ideal image imply
index inner input issue ivory joint judge juice knife knock known label labor
large laser later laugh layer learn least leave legal lemon level light limit
local logic loose lover lower loyal lucky lunch magic major maker march match
maybe mayor meant media mercy metal meter might minor minus model money month
moral motor mount mouse mouth movie music naive nasty nerve never night noble
noise north noted novel nurse ocean offer often older olive onion opera order
organ other ought outer owner paint panel paper party patch peace phase phone
photo piano piece pilot pitch place plain plane plant plate point polar pound
power press price pride prime print prior prize proof proud prove pupil queen
query quick quiet quite quota quote radio raise range rapid ratio reach react
ready realm rebel refer reign relax reply rider right rival river roast robin
robot rocky roman rough round route royal rural salad scale scene scope score
sense serve seven shade shake shall shape share sharp sheep sheet shelf shell
shift shine shirt shock shoot shore short shout shown sight silly since sixth
skill skirt sleep slice slide slope small smart smell smile smoke solar solid
solve sorry sound south space spare speak speed spell spend spice spine split
spoke sport staff stage stair stake stand start state steam steel steep steer
stern stick still stock stone stood store storm story stove strap straw strip
stuck study stuff style sugar suite sunny super sweet swing table taste teach
teeth tempo thank theft their theme there thick thing think third those three
threw throw thumb tiger tight tired title today token tooth topic total touch
tough tower trace track trade trail train treat trend trial tribe trick truck
truly trust truth twice under union unite until upper upset urban usual vague
valid value venue verse video vigor villa vinyl visit vital vivid voice voter
waste watch water weave wedge weigh whale wheat wheel where which while white
whole whose width woman world worry worth would wound write wrong wrote yield
young youth zebra
""".split()
)

assert len(ANSWERS) > 400
assert all(len(w) == 5 and w.isalpha() for w in ANSWERS)
ANSWERS = tuple(sorted(set(ANSWERS)))
