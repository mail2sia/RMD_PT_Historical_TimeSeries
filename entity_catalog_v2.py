"""
ENTITY_CATALOG v2
=================
Normalized, deduplicated catalog for RMD and PT entities.
"""

import unicodedata

# List of abbreviations that require context-aware matching to avoid false positives
RISKY_ABBREVIATIONS = {
    # RMD abbreviations
    "rad": "reactive attachment disorder",
    "ied": "intermittent explosive disorder",
    "npd": "narcissistic personality disorder",
    "stpd": "schizotypal personality disorder",
    "cdd": "childhood disintegrative disorder",
    "ors": "olfactory reference syndrome",
    "kls": "kleine levin syndrome",
    "hpd": "histrionic personality disorder",
    "avpd": "avoidant personality disorder",
    "biid": "body integrity dysphoria",
    "lks": "landau kleffner syndrome",
    "aspd": "antisocial personality disorder",
    "hsam": "hyperthymesia",
    "fdis": "factitious disorder imposed on self",
    # PT abbreviations — neuromodulation / device
    "tms": "transcranial magnetic stimulation",
    "rtms": "repetitive transcranial magnetic stimulation",
    "dtms": "deep transcranial magnetic stimulation",
    "tbs": "theta burst stimulation",
    "vns": "vagus nerve stimulation",
    "ect": "electroconvulsive therapy",
    "bci": "brain computer interface",
    "eeg": "electroencephalography",
    "nibs": "neuromodulation techniques",
    "rsfmri": "resting state functional magnetic resonance imaging",
    "vlsm": "voxel based lesion symptom mapping",
    "vbm": "voxel based lesion symptom mapping",
    # PT abbreviations — pharmacological
    "pgx": "pharmacogenomic testing",
    "fmt": "fecal microbiota transplant",
    "msc": "mesenchymal stem cell therapy",
    # PT abbreviations — digital / devices
    "dtx": "digital therapeutics",
    "pdt": "prescription digital therapeutics",
    "samd": "software as a medical device",
    "aac": "augmentative and alternative communication",
    "sgds": "speech generating devices",
    "eda": "electrodermal activity monitoring",
    "hrv": "heart rate variability monitoring",
    # PT abbreviations — therapy modalities
    "cbt": "cognitive behavioral therapy",
    "dbt": "dialectical behavior therapy",
    "nmt": "music therapy",
    "mi": "motivational interviewing",
    "met": "motivational enhancement therapy",
    "ema": "ecological momentary assessment",
    "ot": "occupational therapy",
    "sst": "social skills training",
    "ipt": "interpersonal psychotherapy",
    "bat": "behavioral activation therapy",
    "cam": "traditional and alternative medicine approaches",
}

# Keywords that should co-occur with risky abbreviations for a valid match
MENTAL_HEALTH_KEYWORDS = [
    "disorder", "diagnosis", "mental", "psychiatric", "symptom", "treatment", "patient", "psychology", "therapy"
]

import re

def is_valid_abbreviation_match(abbrev: str, text: str) -> bool:
    """
    Returns True if the abbreviation appears in a context that suggests it refers to the intended entity.
    For example, 'rad' should only match 'reactive attachment disorder' if near mental health keywords or the full term.
    """
    if abbrev not in RISKY_ABBREVIATIONS:
        return True  # Not risky, accept
    # Check for full term nearby
    full_term = RISKY_ABBREVIATIONS[abbrev]
    if re.search(rf"\b{re.escape(full_term)}\b", text, re.IGNORECASE):
        return True
    # Check for mental health keywords within 5 words of the abbreviation
    for kw in MENTAL_HEALTH_KEYWORDS:
        pattern = rf"\b{abbrev}\b(?:\W+\w+){{0,5}}\b{kw}\b|\b{kw}\b(?:\W+\w+){{0,5}}\b{abbrev}\b"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

# Example usage in data collection pipeline:
# if is_valid_abbreviation_match("rad", some_text):
#     # Accept as 'reactive attachment disorder'
# else:
#     # Ignore or flag for review


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.replace("'", " ").replace("-", " ")
    return " ".join(s.lower().strip().split())


RMD_CATALOG = {
    "reactive attachment disorder": ["reactive attachment disorder", "rad", "attachment disorder", "reactive attachment disorder of infancy"],
    "pyromania": ["pyromania", "pathological fire setting", "incendiarism"],
    "othello syndrome": ["othello syndrome", "morbid jealousy", "delusional jealousy", "pathological jealousy", "sexual jealousy", "conjugal paranoia"],
    "disinhibited social engagement disorder": ["disinhibited social engagement disorder", "dsed", "disinhibited attachment disorder"],
    "schizoaffective disorder": ["schizoaffective disorder", "schizoaffective", "schizo affective psychosis", "schizophreniform psychosis"],
    "erotomania": ["erotomania", "de clerambaults syndrome", "de clerambault syndrome", "erotomanic delusion", "love delusion"],
    "chronic traumatic encephalopathy": ["chronic traumatic encephalopathy", "cte", "dementia pugilistica", "boxers dementia", "punch drunk syndrome"],
    "olfactory reference syndrome": ["olfactory reference syndrome", "ors", "bromidrosiphobia", "olfactory reference disorder"],
    "hypergraphia": ["hypergraphia", "scribomania", "graphomania", "compulsive writing"],
    "wendigo psychosis": ["wendigo psychosis", "witiko psychosis", "windigo syndrome"],
    "body integrity dysphoria": ["body integrity dysphoria", "body integrity identity disorder", "biid", "xenomelia", "apotemnophilia", "transability"],
    "koro": ["koro", "genital retraction syndrome", "shook yong", "suo yang"],
    "dissociative fugue": ["dissociative fugue", "psychogenic fugue", "dissociative amnesia with fugue"],
    "delusional disorder": ["delusional disorder", "paranoid psychosis", "delusional psychosis", "persecutory type delusion"],
    "anorexia nervosa": ["anorexia nervosa", "anorexia", "restricting type anorexia", "binge purge type anorexia", "self starvation"],
    "impulse control disorders": ["impulse control disorders", "impulsivity disorders", "intermittent explosive disorder", "ied"],
    "kleptomania": ["kleptomania", "compulsive stealing", "pathological theft behavior"],
    "postpartum psychosis": ["postpartum psychosis", "puerperal psychosis", "postnatal psychosis", "postpartum mood disorder with psychotic features"],
    "savant syndrome": ["savant syndrome", "savantism", "idiot savant", "acquired savant", "autistic savant"],
    "brief psychotic disorder": ["brief psychotic disorder", "brief reactive psychosis", "atypical psychosis", "bouffee delirante"],
    "schizotypal personality disorder": ["schizotypal personality disorder", "schizotypal", "stpd"],
    "selective mutism": ["selective mutism", "situational mutism", "elective mutism"],
    "kleine levin syndrome": ["kleine levin syndrome", "kls", "sleeping beauty syndrome", "familial hibernation syndrome"],
    "capgras syndrome": ["capgras syndrome", "capgras delusion", "delusion of doubles", "misidentification syndrome"],
    "narcissistic personality disorder": ["narcissistic personality disorder", "npd", "pathological narcissism", "grandiosity"],
    "circadian rhythm sleep wake disorder": ["circadian rhythm sleep wake disorder", "crswd", "sleep wake cycle disorder", "delayed sleep phase disorder"],
    "rumination syndrome": ["rumination syndrome", "merycism", "rumination"],
    "cyclothymic disorder": ["cyclothymic disorder", "cyclothymia", "subthreshold bipolar disorder"],
    "cotard syndrome": ["cotard syndrome", "cotard delusion", "nihilistic delusion", "walking corpse syndrome"],
    "diogenes syndrome": ["diogenes syndrome", "senile squalor syndrome", "severe domestic squalor"],
    "landau kleffner syndrome": ["landau kleffner syndrome", "lks", "acquired epileptic aphasia"],
    "dissociative amnesia": ["dissociative amnesia", "psychogenic amnesia", "functional amnesia"],
    "ekbom syndrome": ["ekbom syndrome", "delusional parasitosis", "formication delusion"],
    "stendhal syndrome": ["stendhal syndrome", "florence syndrome", "art induced psychosis", "hyperkulturemia"],
    "fregoli delusion": ["fregoli delusion", "fregoli syndrome", "the delusion of variations"],
    "reduplicative paramnesia": ["reduplicative paramnesia", "place duplication delusion", "double orientation"],
    "histrionic personality disorder": ["histrionic personality disorder", "hpd", "dramatic personality disorder"],
    "autosarcophagy": ["autosarcophagy", "self cannibalism"],
    "ganser syndrome": ["ganser syndrome", "hysterical pseudodementia", "prison psychosis", "syndrome of approximate answers", "vorbeigehen"],
    "boanthropy": ["boanthropy", "clinical lycanthropy", "zoanthropy"],
    "avoidant personality disorder": ["avoidant personality disorder", "anxious personality disorder", "avpd"],
    "hallucinogen persisting perception disorder": ["hallucinogen persisting perception disorder", "hppd", "perceptual disturbance disorder"],
    "bachmann bupp syndrome": ["bachmann bupp syndrome", "odc1 gain of function syndrome"],
    "factitious disorder": ["factitious disorder", "munchausen syndrome", "factitious disorder imposed on self", "fdis"],
    "hyperthymesia": ["hyperthymesia", "highly superior autobiographical memory", "hsam"],
    "intermetamorphosis syndrome": ["intermetamorphosis syndrome", "intermetamorphosis"],
    "palilalia": ["palilalia", "repetitive speech disorder", "involuntary utterance repetition"],
    "antisocial personality disorder": ["antisocial personality disorder", "aspd", "sociopathy", "psychopathy"],
    "childhood disintegrative disorder": ["childhood disintegrative disorder", "cdd", "heller syndrome", "hellers syndrome"],
}

PT_CATALOG = {
    "transcranial magnetic stimulation": ["transcranial magnetic stimulation", "tms", "rtms", "dtms", "deep tms", "ocd specific rtms", "h coil tms", "theta burst stimulation", "tbs", "prefrontal cortex tms"],
    "deep brain stimulation": ["deep brain stimulation", "dbs", "nucleus accumbens dbs", "stereotactic neurosurgery", "intracranial stimulation"],
    "closed loop neurostimulation": ["closed loop neurostimulation", "responsive neurostimulation", "rns", "brain state dependent stimulation"],
    "transcranial direct current stimulation": ["transcranial direct current stimulation", "tdcs", "tacs", "transcranial electrical stimulation", "tes", "targeted prefrontal tdcs"],
    "vagus nerve stimulation": ["vagus nerve stimulation", "vns", "vagal nerve modulation", "cervical vns", "autonomic dysregulation therapy"],
    "electroconvulsive therapy": ["electroconvulsive therapy", "ect", "brief pulse ect", "ultrabrief ect", "maintenance ect"],
    "focused ultrasound therapy": ["focused ultrasound therapy", "non ablative tfus", "ablative mrgfus", "transcranial focused ultrasound", "tfus"],
    "anticonvulsant therapy": ["anticonvulsant therapy", "antiepileptic drugs", "aeds", "corticosteroid therapy", "ivig immunotherapy", "epilepsy drug therapy"],
    "light therapy": ["light therapy", "phototherapy", "bright light therapy", "sad light therapy"],
    "chronotherapy": ["chronotherapy", "sleep phase advancement", "circadian realignment therapy", "sleep schedule manipulation"],
    "immunotherapy for neuropsychiatric disorders": ["immunotherapy for neuropsychiatric disorders", "ivig neuropsychiatric protocol", "autoimmune encephalopathy treatment", "rituximab therapy", "plasmapheresis"],
    "antipsychotic medications": ["antipsychotic medications", "neuroleptics", "dopamine antagonists", "long acting injectables", "lais", "atypical antipsychotics"],
    "clozapine protocol": ["clozapine protocol", "clozaril", "treatment resistant antipsychotic", "clozapine titration"],
    "selective serotonin reuptake inhibitors": ["selective serotonin reuptake inhibitors", "ssris", "ssri therapy"],
    "antidepressants": ["antidepressants", "snris", "tcas", "maois", "ndris", "atypical antidepressants"],
    "mood stabilizers": ["mood stabilizers", "lithium carbonate", "valproate", "lamotrigine", "antiepileptic mood agents"],
    "lithium therapy": ["lithium therapy", "lithium for sleep regulation", "lithium maintenance therapy"],
    "stimulant and wake promoting agents": ["stimulant and wake promoting agents", "modafinil", "armodafinil", "methylphenidate", "wakefulness promoting drugs"],
    "oxytocin therapy": ["oxytocin therapy", "intranasal oxytocin", "neuropeptide attachment therapy", "prosocial neuropeptide treatment"],
    "ketamine therapy": ["ketamine therapy", "esketamine", "spravato", "ketamine infusion therapy", "ketamine assisted psychotherapy"],
    "psilocybin assisted therapy": ["psilocybin assisted therapy", "psilocybin treatment", "entheogenic therapy", "psychedelic assisted therapy", "mdma assisted therapy"],
    "anxiolytic medications": ["anxiolytic medications", "anxiolytics", "anti anxiety medications", "benzodiazepines"],
    "naltrexone": ["naltrexone", "opioid antagonist therapy", "naltrexone treatment"],
    "metabolic and enzyme targeted therapy": ["metabolic and enzyme targeted therapy", "dfmo", "difluoromethylornithine", "odc1 enzyme inhibition", "polyamine pathway therapy"],
    "pharmacogenomic testing": ["pharmacogenomic testing", "cytochrome p450 testing", "pgx", "genetic screening for medication response"],
    "neuroprotective agents": ["neuroprotective agents", "nootropics", "cognitive enhancers", "brain supplements", "amyloid targeted therapies"],
    "cognitive behavioral therapy": ["cognitive behavioral therapy", "cbt", "manualized psychotherapy", "psychotherapeutic treatment"],
    "cbt for insomnia": ["cbt for insomnia", "cbt i", "digital cbt i", "sleep restriction therapy"],
    "dialectical behavior therapy": ["dialectical behavior therapy", "dbt", "emotional regulation training", "dbt skills groups"],
    "emdr therapy": ["emdr therapy", "eye movement desensitization and reprocessing", "eye movement therapy", "emdr"],
    "acceptance and commitment therapy": ["acceptance and commitment therapy", "act", "psychological flexibility training"],
    "trauma focused cbt": ["trauma focused cbt", "tf cbt", "ptsd specific cbt"],
    "prolonged exposure therapy": ["prolonged exposure therapy", "pe therapy", "imaginal exposure", "in vivo exposure therapy"],
    "reality testing techniques": ["reality testing techniques", "cognitive reality checking", "delusion assessment"],
    "mindfulness based stress reduction": ["mindfulness based stress reduction", "mbsr", "mbct", "mindfulness based cognitive therapy"],
    "schema therapy": ["schema therapy", "schema focused therapy", "early maladaptive schema therapy", "young schema therapy"],
    "mentalization based treatment": ["mentalization based treatment", "mbt", "reflective functioning therapy", "mentalization therapy"],
    "motivational interviewing": ["motivational interviewing", "mi", "motivational enhancement therapy", "met"],
    "narrative exposure therapy": ["narrative exposure therapy", "net", "testimony therapy", "life narrative reconstruction"],
    "transference focused psychotherapy": ["transference focused psychotherapy", "tfp", "object relations therapy", "psychodynamic personality therapy"],
    "hypnotherapy": ["hypnotherapy", "clinical hypnosis", "hypnoanalysis", "ego strengthening hypnosis"],
    "cultural psychiatry interventions": ["cultural psychiatry interventions", "ethnocultural healing", "culture bound syndrome protocols", "transcultural psychiatry"],
    "neurofeedback": ["neurofeedback", "eeg biofeedback", "fmri neurofeedback", "heg biofeedback", "eeg neurobiofeedback"],
    "music therapy": ["music therapy", "neurologic music therapy", "nmt", "receptive music therapy", "active music therapy"],
    "art therapy": ["art therapy", "visual art therapy", "expressive arts therapy", "art psychotherapy"],
    "animal assisted therapy": ["animal assisted therapy", "aat", "therapy animal intervention", "equine assisted therapy", "canine assisted therapy"],
    "social skills training": ["social skills training", "sst", "interpersonal effectiveness training", "social competence training"],
    "occupational therapy": ["occupational therapy", "ot", "functional skills rehabilitation", "activities of daily living training", "adl training"],
    "augmentative and alternative communication": ["augmentative and alternative communication", "aac", "aac devices", "speech generating devices", "sgds", "voice output communication aids"],
    "speech language therapy": ["speech language therapy", "speech and language therapy", "speech therapy"],
    "digital phenotyping": ["digital phenotyping", "passive sensing", "smartphone sensing", "behavioral biomarkers", "ecological momentary assessment", "ema"],
    "vocal and speech biomarkers": ["vocal and speech biomarkers", "acoustic analysis", "prosody extraction", "clinical speech analysis", "vocal biomarker profiling"],
    "generative ai diagnostics": ["generative ai diagnostics", "llm based symptom screening", "synthesized clinical reports", "predictive risk modeling", "ai symptom tracking"],
    "machine learning neuroimaging": ["machine learning neuroimaging", "radiomics", "automated brain volume analysis", "connectomic profiling", "voxel based morphometry ml"],
    "digital therapeutics": ["digital therapeutics", "dtx", "samd", "software as a medical device", "prescription digital therapeutics", "pdt"],
    "vr and ar therapy": ["vr and ar therapy", "virtual reality exposure therapy", "vret", "augmented reality therapy", "ar therapy", "immersive behavioral training", "avatar therapy"],
    "serious games for health": ["serious games for health", "gamified cognitive remediation", "digital brain training", "neuroplasticity games"],
    "brain computer interface": ["brain computer interface", "bci", "direct neural interface", "neural bypass"],
    "stem cell neuro therapy": ["stem cell neuro therapy", "neural stem cell transplantation", "regenerative medicine", "msc therapy"],
    "fecal microbiota transplant": ["fecal microbiota transplant", "fmt", "gut brain axis therapy", "psychobiotics"],
    "smart wearable mental health trackers": ["smart wearable mental health trackers", "actigraphy", "electrodermal activity monitoring", "eda", "heart rate variability monitoring", "hrv tracking", "wearable eeg"],
    "polysomnography guided sleep intervention": ["polysomnography guided sleep intervention", "psg sleep study", "sleep architecture analysis", "overnight sleep monitoring"],
    "digital health tools": ["digital health tools", "mobile health apps", "mhealth applications", "ehealth tools", "telehealth platforms", "digital health interventions", "remote patient monitoring"],
    "cognitive assistive technologies": ["cognitive assistive technologies", "cognitive aids", "ai cognitive aids", "assistive cognitive devices", "memory aid technology", "cognitive support apps", "cognitive prosthetics"],
    "electroencephalography": ["electroencephalography", "eeg", "quantitative eeg", "qeeg", "ambulatory eeg", "brain electrical activity mapping", "sleep eeg"],
    "biofeedback devices": ["biofeedback devices", "physiological biofeedback", "electromyography biofeedback", "emg biofeedback", "thermal biofeedback", "galvanic skin response biofeedback"],
    "metaverse": ["metaverse", "immersive virtual environments", "extended reality", "xr therapy", "metaverse mental health", "virtual social environments"],
    "personalized medicine": ["personalized medicine", "precision psychiatry", "precision medicine", "biomarker guided therapy", "stratified medicine", "individualized treatment planning"],
    "neuromodulation techniques": ["neuromodulation techniques", "non invasive brain stimulation", "nibs", "peripheral neuromodulation", "brain modulation therapy", "central neuromodulation"],
    "resting state functional magnetic resonance imaging": ["resting state functional magnetic resonance imaging", "rs fmri", "resting state fmri", "functional connectivity mri", "brain network mapping", "default mode network imaging"],
    "voxel based lesion symptom mapping": ["voxel based lesion symptom mapping", "vlsm", "voxel based morphometry", "vbm", "lesion symptom mapping", "brain lesion analysis"],
    "neuroplasticity techniques": ["neuroplasticity techniques", "cognitive rehabilitation", "brain adaptation training", "neuroplasticity training", "experience dependent plasticity", "brain rewiring therapy"],
    "blockchain for data protection": ["blockchain for data protection", "decentralized health records", "blockchain ehr", "distributed ledger healthcare", "encrypted healthcare records", "decentralized data security"],
    "privacy preserving ai in digital mental health": ["privacy preserving ai in digital mental health", "federated learning psychiatry", "differential privacy healthcare", "secure ai mental health", "confidential computing health"],
    "secure data storage for patient records": ["secure data storage for patient records", "hipaa compliant cloud storage", "electronic health records security", "ehr encryption", "health data protection", "patient data security"],
    "digital imaging technologies for brain scanning": ["digital imaging technologies for brain scanning", "neuroimaging ai", "medical brain imaging", "ai brain scan analysis", "automated neuroimaging", "ct brain scanning ai"],
    "neurobiological assessments for mental disorders": ["neurobiological assessments for mental disorders", "psychiatric biomarkers", "brain function testing", "neurobiological profiling", "blood based biomarkers mental health", "biomarker analysis psychiatry"],
    "psychophysiological metrics for treatment response": ["psychophysiological metrics for treatment response", "heart rate variability treatment", "cortisol monitoring therapy", "autonomic nervous system monitoring", "physiological treatment markers", "psychophysiological monitoring"],
    "interpersonal psychotherapy": ["interpersonal psychotherapy", "ipt therapy", "dynamic interpersonal therapy", "relationship focused therapy", "interpersonal therapy depression"],
    "psychoeducation programs": ["psychoeducation programs", "mental health education", "illness management training", "psychoeducational intervention", "patient education psychiatry", "family psychoeducation"],
    "neurocognitive training": ["neurocognitive training", "cognitive training program", "working memory training", "attention training program", "executive function training", "computerized cognitive training"],
    "meditation and relaxation techniques": ["meditation and relaxation techniques", "mindfulness meditation", "deep breathing exercises", "progressive muscle relaxation", "relaxation training", "guided meditation stress reduction"],
    "expressive writing and journaling": ["expressive writing and journaling", "therapeutic writing", "emotional expression writing", "narrative journaling", "written emotional disclosure", "expressive writing therapy"],
    "behavioral activation therapy": ["behavioral activation therapy", "bat therapy", "depression behavioral therapy", "activity scheduling therapy", "behavioral activation treatment", "pleasure mastery activities"],
    "peer support programs and online communities": ["peer support programs and online communities", "mental health peer support", "peer specialist programs", "peer recovery support", "online mental health communities", "peer led support groups"],
    "memory retrieval techniques": ["memory retrieval techniques", "cognitive recall training", "mnemonic strategies", "retrieval practice therapy", "spaced retrieval training", "memory enhancement therapy"],
    "cognitive enhancement programs": ["cognitive enhancement programs", "brain training apps", "neuroplasticity exercises", "cognitive fitness programs", "cognitive stimulation therapy", "computerized brain training"],
    "dietary interventions and supplements": ["dietary interventions and supplements", "nutritional psychiatry", "omega 3 therapy", "gut microbiome diet mental health", "nutraceuticals psychiatry", "anti inflammatory diet mental health"],
    "traditional and alternative medicine approaches": ["traditional and alternative medicine approaches", "ayurveda mental health", "acupuncture psychiatry", "herbal remedies mental health", "complementary alternative medicine", "traditional chinese medicine psychiatry"],
    "regenerative medicine approaches": ["regenerative medicine approaches", "tissue engineering psychiatry", "cell based therapies neurology", "biologic repair neurological", "regenerative neurology"],
    "sleep pattern monitoring and manipulation": ["sleep pattern monitoring and manipulation", "sleep hygiene coaching", "insomnia therapy", "sleep tracking technology", "actigraphy sleep monitoring", "sleep diary intervention"],
}

RMD_TO_PT = {
    "reactive attachment disorder": ["oxytocin therapy", "cognitive behavioral therapy", "dialectical behavior therapy", "animal assisted therapy", "social skills training", "mentalization based treatment", "psychoeducation programs", "biofeedback devices", "peer support programs and online communities", "psychophysiological metrics for treatment response"],
    "pyromania": ["cognitive behavioral therapy", "dialectical behavior therapy", "motivational interviewing", "selective serotonin reuptake inhibitors", "deep brain stimulation", "psychoeducation programs", "behavioral activation therapy"],
    "othello syndrome": ["antipsychotic medications", "cognitive behavioral therapy", "schema therapy", "transference focused psychotherapy", "interpersonal psychotherapy", "psychoeducation programs"],
    "disinhibited social engagement disorder": ["oxytocin therapy", "cognitive behavioral therapy", "social skills training", "animal assisted therapy", "psychoeducation programs", "metaverse", "digital health tools"],
    "schizoaffective disorder": ["antipsychotic medications", "clozapine protocol", "mood stabilizers", "transcranial magnetic stimulation", "cognitive behavioral therapy", "digital phenotyping", "smart wearable mental health trackers", "psychoeducation programs", "interpersonal psychotherapy", "personalized medicine", "neuromodulation techniques", "resting state functional magnetic resonance imaging", "neurobiological assessments for mental disorders", "psychophysiological metrics for treatment response", "digital health tools", "behavioral activation therapy", "peer support programs and online communities", "sleep pattern monitoring and manipulation"],
    "erotomania": ["antipsychotic medications", "cognitive behavioral therapy", "reality testing techniques", "interpersonal psychotherapy", "psychoeducation programs"],
    "chronic traumatic encephalopathy": ["neuroprotective agents", "cognitive behavioral therapy", "neurofeedback", "smart wearable mental health trackers", "digital phenotyping", "electroencephalography", "resting state functional magnetic resonance imaging", "voxel based lesion symptom mapping", "neuroplasticity techniques", "neurocognitive training", "cognitive enhancement programs", "regenerative medicine approaches", "neurobiological assessments for mental disorders", "digital imaging technologies for brain scanning", "personalized medicine"],
    "olfactory reference syndrome": ["selective serotonin reuptake inhibitors", "cognitive behavioral therapy", "acceptance and commitment therapy", "meditation and relaxation techniques", "psychoeducation programs"],
    "hypergraphia": ["mood stabilizers", "cognitive behavioral therapy", "occupational therapy", "expressive writing and journaling", "meditation and relaxation techniques", "behavioral activation therapy"],
    "wendigo psychosis": ["antipsychotic medications", "cultural psychiatry interventions", "cognitive behavioral therapy", "traditional and alternative medicine approaches"],
    "body integrity dysphoria": ["cognitive behavioral therapy", "schema therapy", "transcranial magnetic stimulation", "selective serotonin reuptake inhibitors", "psychoeducation programs", "peer support programs and online communities", "digital health tools", "neurobiological assessments for mental disorders"],
    "koro": ["cultural psychiatry interventions", "cognitive behavioral therapy", "antidepressants", "anxiolytic medications", "traditional and alternative medicine approaches", "meditation and relaxation techniques"],
    "dissociative fugue": ["hypnotherapy", "narrative exposure therapy", "emdr therapy", "trauma focused cbt", "cognitive behavioral therapy", "memory retrieval techniques", "expressive writing and journaling"],
    "delusional disorder": ["antipsychotic medications", "cognitive behavioral therapy", "schema therapy", "psychoeducation programs", "neurobiological assessments for mental disorders", "personalized medicine"],
    "anorexia nervosa": ["cognitive behavioral therapy", "dialectical behavior therapy", "electroconvulsive therapy", "deep brain stimulation", "selective serotonin reuptake inhibitors", "occupational therapy", "art therapy", "dietary interventions and supplements", "psychoeducation programs", "peer support programs and online communities", "digital health tools", "behavioral activation therapy"],
    "impulse control disorders": ["cognitive behavioral therapy", "dialectical behavior therapy", "motivational interviewing", "deep brain stimulation", "selective serotonin reuptake inhibitors", "mood stabilizers", "biofeedback devices", "meditation and relaxation techniques", "neuromodulation techniques", "psychophysiological metrics for treatment response", "dietary interventions and supplements", "digital health tools"],
    "kleptomania": ["cognitive behavioral therapy", "motivational interviewing", "deep brain stimulation", "selective serotonin reuptake inhibitors", "naltrexone", "psychoeducation programs", "behavioral activation therapy", "peer support programs and online communities"],
    "postpartum psychosis": ["electroconvulsive therapy", "antipsychotic medications", "mood stabilizers", "cognitive behavioral therapy", "psychoeducation programs", "peer support programs and online communities", "digital health tools", "expressive writing and journaling"],
    "savant syndrome": ["occupational therapy", "music therapy", "art therapy", "augmentative and alternative communication", "neurofeedback", "transcranial direct current stimulation", "cognitive assistive technologies", "neurocognitive training", "cognitive enhancement programs", "neuroplasticity techniques"],
    "brief psychotic disorder": ["antipsychotic medications", "cognitive behavioral therapy", "mindfulness based stress reduction", "psychoeducation programs", "peer support programs and online communities"],
    "schizotypal personality disorder": ["antipsychotic medications", "cognitive behavioral therapy", "social skills training", "transcranial direct current stimulation", "psychoeducation programs", "personalized medicine", "resting state functional magnetic resonance imaging", "neurocognitive training"],
    "selective mutism": ["cognitive behavioral therapy", "selective serotonin reuptake inhibitors", "augmentative and alternative communication", "music therapy", "animal assisted therapy", "metaverse", "digital health tools", "psychoeducation programs"],
    "kleine levin syndrome": ["lithium therapy", "stimulant and wake promoting agents", "polysomnography guided sleep intervention", "chronotherapy", "vagus nerve stimulation", "electroencephalography", "sleep pattern monitoring and manipulation", "digital health tools", "neurobiological assessments for mental disorders"],
    "capgras syndrome": ["antipsychotic medications", "cognitive behavioral therapy", "reality testing techniques", "psychoeducation programs", "neurobiological assessments for mental disorders", "digital imaging technologies for brain scanning", "voxel based lesion symptom mapping"],
    "narcissistic personality disorder": ["schema therapy", "transference focused psychotherapy", "mentalization based treatment", "cognitive behavioral therapy", "interpersonal psychotherapy"],
    "circadian rhythm sleep wake disorder": ["light therapy", "chronotherapy", "cbt for insomnia", "mood stabilizers", "smart wearable mental health trackers", "sleep pattern monitoring and manipulation", "digital health tools", "polysomnography guided sleep intervention"],
    "rumination syndrome": ["cognitive behavioral therapy", "dialectical behavior therapy", "mindfulness based stress reduction", "occupational therapy", "meditation and relaxation techniques", "dietary interventions and supplements"],
    "cyclothymic disorder": ["mood stabilizers", "lithium therapy", "cognitive behavioral therapy", "light therapy", "vagus nerve stimulation", "transcranial magnetic stimulation", "interpersonal psychotherapy", "psychoeducation programs", "biofeedback devices", "dietary interventions and supplements", "sleep pattern monitoring and manipulation", "psychophysiological metrics for treatment response", "personalized medicine"],
    "cotard syndrome": ["electroconvulsive therapy", "antipsychotic medications", "mood stabilizers", "ketamine therapy", "art therapy", "behavioral activation therapy", "sleep pattern monitoring and manipulation"],
    "diogenes syndrome": ["cognitive behavioral therapy", "motivational interviewing", "occupational therapy", "social skills training", "peer support programs and online communities", "digital health tools", "psychoeducation programs"],
    "landau kleffner syndrome": ["anticonvulsant therapy", "immunotherapy for neuropsychiatric disorders", "augmentative and alternative communication", "music therapy", "speech language therapy", "electroencephalography", "voxel based lesion symptom mapping", "digital imaging technologies for brain scanning"],
    "dissociative amnesia": ["hypnotherapy", "emdr therapy", "narrative exposure therapy", "trauma focused cbt", "cognitive behavioral therapy", "memory retrieval techniques", "expressive writing and journaling"],
    "ekbom syndrome": ["antipsychotic medications", "cognitive behavioral therapy", "selective serotonin reuptake inhibitors", "meditation and relaxation techniques", "biofeedback devices", "traditional and alternative medicine approaches"],
    "stendhal syndrome": ["cognitive behavioral therapy", "art therapy", "mindfulness based stress reduction", "antidepressants", "meditation and relaxation techniques", "expressive writing and journaling"],
    "fregoli delusion": ["antipsychotic medications", "cognitive behavioral therapy", "psychoeducation programs", "neurobiological assessments for mental disorders", "digital imaging technologies for brain scanning"],
    "reduplicative paramnesia": ["antipsychotic medications", "cognitive behavioral therapy", "reality testing techniques", "neurobiological assessments for mental disorders", "digital imaging technologies for brain scanning", "voxel based lesion symptom mapping"],
    "histrionic personality disorder": ["schema therapy", "transference focused psychotherapy", "dialectical behavior therapy", "cognitive behavioral therapy", "interpersonal psychotherapy"],
    "autosarcophagy": ["antipsychotic medications", "electroconvulsive therapy", "dialectical behavior therapy", "psychoeducation programs", "peer support programs and online communities"],
    "ganser syndrome": ["hypnotherapy", "cognitive behavioral therapy", "art therapy", "antipsychotic medications", "expressive writing and journaling"],
    "boanthropy": ["antipsychotic medications", "cultural psychiatry interventions", "cognitive behavioral therapy", "traditional and alternative medicine approaches"],
    "avoidant personality disorder": ["schema therapy", "cognitive behavioral therapy", "acceptance and commitment therapy", "social skills training", "animal assisted therapy", "selective serotonin reuptake inhibitors", "interpersonal psychotherapy", "metaverse", "peer support programs and online communities", "meditation and relaxation techniques"],
    "hallucinogen persisting perception disorder": ["cognitive behavioral therapy", "prolonged exposure therapy", "selective serotonin reuptake inhibitors", "antipsychotic medications", "neurofeedback", "meditation and relaxation techniques", "biofeedback devices", "digital health tools"],
    "bachmann bupp syndrome": ["metabolic and enzyme targeted therapy", "pharmacogenomic testing", "augmentative and alternative communication", "occupational therapy", "personalized medicine", "neurobiological assessments for mental disorders", "regenerative medicine approaches"],
    "factitious disorder": ["cognitive behavioral therapy", "mentalization based treatment", "schema therapy", "motivational interviewing", "psychoeducation programs", "peer support programs and online communities"],
    "hyperthymesia": ["cognitive behavioral therapy", "mindfulness based stress reduction", "neurofeedback", "digital phenotyping", "memory retrieval techniques", "meditation and relaxation techniques"],
    "intermetamorphosis syndrome": ["antipsychotic medications", "cognitive behavioral therapy", "neurobiological assessments for mental disorders", "digital imaging technologies for brain scanning"],
    "palilalia": ["antipsychotic medications", "transcranial magnetic stimulation", "augmentative and alternative communication", "occupational therapy", "speech language therapy", "digital health tools", "biofeedback devices"],
    "antisocial personality disorder": ["schema therapy", "mentalization based treatment", "cognitive behavioral therapy", "dialectical behavior therapy", "motivational interviewing", "psychoeducation programs", "peer support programs and online communities", "cognitive assistive technologies"],
    "childhood disintegrative disorder": ["augmentative and alternative communication", "occupational therapy", "social skills training", "music therapy", "antipsychotic medications", "cognitive assistive technologies", "neurocognitive training", "cognitive enhancement programs", "digital health tools", "psychoeducation programs"],
}

PT_TO_RMD: dict = {}
for rmd, pts in RMD_TO_PT.items():
    for pt in pts:
        PT_TO_RMD.setdefault(pt, []).append(rmd)


def _dedupe_norm_list(items: list[str]) -> list[str]:
    out = []
    seen = set()
    for x in items:
        n = normalize(x)
        if n and n not in seen:
            out.append(n)
            seen.add(n)
    return out


for _k, _vals in list(RMD_CATALOG.items()):
    RMD_CATALOG[_k] = _dedupe_norm_list(_vals)

for _k, _vals in list(PT_CATALOG.items()):
    PT_CATALOG[_k] = _dedupe_norm_list(_vals)
