import pandas as pd
import re
from collections import defaultdict
from datetime import datetime

# ==== CONFIG ====
csv_path = 'C:/Users/Ahsan/Downloads/RMDs-and-PTs-main/Patents/merged_cleaned_patents.csv'
output_csv = 'C:/Users/Ahsan/Downloads/RMDs-and-PTs-main/Patents/patent_mentions_final.csv'

# ==== SEARCH TERMS ====
SEARCH_TERMS = {
    "Digital Health Tools": ["Mobile Health Apps", "Health Information Technology", "Health Monitoring Wearable Devices", "Telehealth", "Telemedicine", "Personalized Medicine", "Care Support Tools"],
    "Virtual Reality Exposure Therapy": ["VR Exposure Therapy", "Virtual Reality Therapy", "VR Immersion Therapy", "Simulated Therapy", "Computerized CBT", "Computerized Cognitive Behavioral Therapy"],
    "Brain Stimulation Technologies": ["Neurostimulation Techniques", "Deep brain stimulation"],
    "Eye Movement Desensitization and Reprocessing": ["EMDR Therapy", "eye movement therapy"],
    "Cognitive Assistive Technologies": ["AI Cognitive Aids"],
    "Electroencephalography": ["EEG", "Brain Activity Scanning"],
    "Transcranial Magnetic Stimulation": ["Repetitive Transcranial Magnetic Stimulation", "Non-Invasive Brain Stimulation"],
    "Brain-Computer Interface": ["Direct Neural Interface", "Neural Interface"],
    "Augmentative Communication Devices": ["Speech Generating Devices", "Speech Assistive Tools", "Text-to-Speech Devices"],
    "Neurofeedback Systems": ["EEG Biofeedback Therapy", "Neurobiofeedback"],
    "Biofeedback Devices": ["Physiological Monitoring Tools"],
    "Metaverse": ["Immersive Virtual Environments", "Extended Reality"],
    "Genetic Testing": ["Genetic Screening", "Genomic Screening", "DNA Profiling"],
    "Personalized Medicine": ["Precision Medicine", "Customized Medicine"],
    "Neuromodulation Techniques": ["Vagus Nerve Stimulation", "Brain Modulation", "Deep Brain Stimulation", "Spinal Cord Stimulation"],
    "Resting-state Functional Magnetic Resonance Imaging": ["rs-fMRI", "Brain Network Mapping"],
    "Voxel-based Lesion-Symptom Mapping": ["Voxel-Based Symptom-Lesion Mapping", "Neuroimaging Analysis"],
    "Neuroplasticity Techniques": ["Cognitive Rehabilitation", "Brain Adaptation Training"],
    "Blockchain for Data Protection": ["Decentralized Data Security", "Encrypted Healthcare Records"],
    "Privacy-Preserving AI in Digital Mental Health": ["Federated Learning", "Secure AI Models"],
    "Secure Data Storage for Patient Records": ["HIPAA-Compliant Cloud Storage", "Health Information Security", "Electronic Health Record Protection"],
    "Smart Wearable Mental Health Trackers": ["AI-Powered Wearables", "Digital Biomarkers"],
    "Digital Imaging Technologies for Brain Scanning": ["Neuroimaging AI", "Medical Image Analysis"],
    "Cognitive Behavioral Therapy": ["Psychotherapeutic Treatment"],
    "Dialectical Behavior Therapy": ["Emotional Regulation Therapy"],
    "Trauma-Focused CBT": ["TF-CBT", "PTSD Therapy"],
    "Exposure Therapy": ["Systematic Desensitization", "Gradual Exposure Therapy"],
    "Mindfulness-Based Stress Reduction": ["Mindfulness-Based Cognitive Therapy", "Mindfulness Therapy", "Dialectical Behavior Therapy"],
    "Interpersonal Psychotherapy": ["Dynamic Interpersonal Therapy", "Relationship-Focused Therapy"],
    "Reality Testing Techniques": ["Cognitive Reality Checking", "Delusion Assessment"],
    "Psychoeducation Programs": ["Mental Health Awareness Training"],
    "Neurocognitive Training": ["Cognitive Enhancement Exercises"],
    "Antipsychotic Medications": ["Neuroleptics", "Dopamine Antagonists"],
    "Selective Serotonin Reuptake Inhibitors": ["SSRIs", "Antidepressant Therapy"],
    "Benzodiazepines": ["Anxiolytics", "Sedative-Hypnotics"],
    "Mood Stabilizers": ["Lithium", "Valproate", "Bipolar Treatment"],
    "Antidepressants": ["MAOIs", "TCAs", "SSRIs", "SNRIs"],
    "Neuroprotective Agents": ["Cognitive Enhancers", "Brain Health Supplements"],
    "Meditation and Relaxation Techniques": ["Mindfulness Meditation", "Deep Breathing Exercises"],
    "Creative Arts Therapies": ["Music Therapy", "Art Therapy", "Expressive Therapy"],
    "Expressive Writing & Journaling": ["Therapeutic Writing", "Emotional Expression"],
    "Animal-Assisted Interventions": ["Therapy Animals", "Emotional Support Animals"],
    "Dietary Interventions & Supplements": ["Nutritional Psychiatry", "Omega-3 Therapy"],
    "Traditional & Alternative Medicine Approaches": ["Ayurveda", "Acupuncture", "Herbal Remedies"],
    "Memory Retrieval Techniques": ["Cognitive Recall Training", "Mnemonic Strategies"],
    "Cognitive Enhancement Programs": ["Neuroplasticity Exercises", "Brain Training Apps"],
    "Social Skills Training": ["Interpersonal Effectiveness Training", "Autism Social Therapy"],
    "Emotion Regulation Training": ["DBT Emotion Skills", "Mindfulness Emotion Awareness"],
    "Behavioral Activation Therapy": ["BAT", "Depression Behavioral Therapy"],
    "Peer Support Programs & Online Communities": ["Mental Health Peer Networks"],
    "Stem Cell Therapy for Neurological Disorders": ["Regenerative Medicine", "Neural Repair"],
    "Regenerative Medicine Approaches": ["Tissue Engineering", "Organ Regeneration"],
    "Neurobiological Assessments for Mental Disorders": ["Brain Function Testing", "Biomarker Analysis"],
    "Sleep Pattern Monitoring & Manipulation": ["Sleep Hygiene Coaching", "Insomnia Therapy"],
    "Psychophysiological Metrics for Treatment Response": ["Heart Rate Variability", "Cortisol Levels"],
    "Reactive Attachment": [],
    "Pyromania": ["Pathological Fire Setting"],
    "Othello": ["Morbid Jealousy", "Delusional Jealousy", "Pathological Jealousy", "Sexual Jealousy"],
    "Disinhibited Social Engagement": ["Disinhibited Attachment"],
    "Schizoaffective": ["Schizo-affective Psychosis", "Schizo-affective Schizophrenia", "Schizophreniform Psychosis"],
    "Erotomanic": ["De Clérambault's", "De Clérambault", "De Clérambaults", "Love Delusion", "Erotomania"],
    "Dementia pugilistica": ["Punch Drunk", "Chronic Traumatic Encephalopathy"],
    "Olfactory Reference": [],
    "Hypergraphia": [],
    "Wendigo Psychosis": ["Witiko Psychosis"],
    "Body Integrity Dysphoria": ["Body Integrity Identity", "Xenomelia", "Apotemnophilia", "Amputee Identity"],
    "koro": ["genital retraction"],
    "Dissociative Fugue": ["Psychogenic Fugue", "Dissociative Amnesia with Fugue"],
    "Delusional": ["Paranoia"],
    "Anorexia nervosa": ["Anorexia"],
    "Impulse Control": ["Impulsivity"],
    "Postpartum Psychosis": ["Puerperal Psychosis", "Postnatal Psychosis"],
    "Savant": ["Savantism", "idiot savant"],
    "Brief Psychotic": ["Brief Reactive Psychosis", "Atypical Psychosis", "Bouffée Délirante"],
    "Schizotypal Personality": ["Schizotypal"],
    "Selective Mutism": ["Situational Mutism"],
    "Kleine-Levin": ["Familial Hibernation", "Sleeping Beauty"],
    "Capgras": ["Delusion of Doubles"],
    "Narcissistic Personality": ["Narcissistic Personality", "Grandiosity"],
    "Circadian Rhythm Sleep-Wake": ["Sleep-wake cycle"],
    "Rumination": ["Merycism"],
    "Cyclothymic": ["Cyclothymia", "Bipolar III"],
    "Walking Corpse": ["Cotard Delusion"],
    "Diogenes": ["Senile Squalor"],
    "Landau-Kleffner": ["Acquired Epileptic Aphasia"],
    "Psychogenic Amnesia": ["Dissociative Amnesia"],
    "Ekbom": ["Willis-Ekbom", "restless legs"],
    "Stendhal": ["Florence", "Art-Induced Psychosis"],
    "Fregoli Delusion": ["Fregoli"],
    "Reduplicative Paramnesia": ["Memory Confusion"],
    "Histrionic Personality": ["Dramatic Personality"],
    "Autosarcophagy": ["Self-Cannibalism"],
    "Ganser": ["hysterical pseudodementia", "prison psychosis", "balderdash", "Vorbeigehen", "Vorbeireden"],
    "Kleptomania": ["Compulsive Stealing"],
    "Boanthropy": ["Clinical Lycanthropy"],
    "Avoidant Personality": ["anxious personality"],
    "Hallucinogen-Induced Psychotic": ["Drug-Induced Psychosis", "Psychedelic Psychosis"],
    "Bachmann-Bupp": ["ODC1 Gain-of-Function"],
    "Factitious": ["Munchausen"],
    "Hyperthymesia": ["Highly Superior Autobiographical Memory"],
    "Intermetamorphosis": [],
    "Palilalia": ["Repetitive Speech"],
    "Scribomania": ["Graphomania"],
    "Antisocial Personality Disorder": [],
    "Childhood Disintegrative Disorder": ["Heller’s syndrome", "Heller syndrome", "Hellers syndrome"]
}


# ==== Reverse Lookup ====
TERM_TO_MAIN = {}
for main, synonyms in SEARCH_TERMS.items():
    TERM_TO_MAIN[main.lower()] = main
    for syn in synonyms:
        TERM_TO_MAIN[syn.lower()] = main

# ==== Load CSV ====
df = pd.read_csv(csv_path)

# Normalize column names
df.columns = [col.strip().lower().replace(" ", "_") for col in df.columns]

# Convert publication_date
df['publication_date'] = pd.to_datetime(df['publication_date'], errors='coerce')

# Fields to search
text_fields = ['title', 'abstract', 'summary', 'content']
fields_to_scan = [f for f in text_fields if f in df.columns]

# ==== Count Mentions ====
mention_counts = defaultdict(int)
output_rows = []

for _, row in df.iterrows():
    pub_date = row.get('publication_date')
    if pd.isna(pub_date):
        continue

    month = pub_date.strftime('%m-%Y')
    combined_text = ' '.join(str(row.get(f, '')).lower() for f in fields_to_scan)

    matched_terms = set()
    for keyword in TERM_TO_MAIN:
        if re.search(r'\b' + re.escape(keyword) + r'\b', combined_text):
            matched_terms.add(TERM_TO_MAIN[keyword])

    for term in matched_terms:
        mention_counts[(month, term)] += 1
        nom = mention_counts[(month, term)]
        output_rows.append((month, nom, term))

# ==== Save Output ====
result_df = pd.DataFrame(output_rows, columns=['Date', 'NoM', 'Main_Term']).drop_duplicates()
result_df.to_csv(output_csv, index=False)

print(f"✅ Done! Saved {len(result_df)} records to: {output_csv}")