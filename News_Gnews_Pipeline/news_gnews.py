import requests
import csv
import time
import random
import os
import urllib.parse
from collections import defaultdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from tqdm import tqdm

# ==== Config ====
API_KEYS = [
    "556914b73d45d537222c67e536c9c276", "6f1faa3087ebd3e79b1bb29d886d862d",
    "9154e3a1b915ec4c2ad8b9b526cd265d", "6be276469ff1d608ec5bb22c821f9b2c",
    "73316fa5cee173dec407e6fd13d5493d", "3a10bd1f5e44b1e5d5d928c172d50f21",
    "51c713e97fdef85405856d0c67900d1b", "b87047ebef28b088105cc0b0400800bc",
    "18f6dd68a40887fb6ad7fd95f17916e5", "81246f8e958d829ff46388e1325efc66",
    "5fc039e91dcd57a32cc34b066066eccf", "cfbd0eaa7eef107e0f7b275901ca2dfd"
]

MAX_REQUESTS_PER_KEY = 2500
key_usage = [0] * len(API_KEYS)
keys_exhausted_warned = False

START_MONTH = "2004-01"
END_MONTH = "2026-02"

YEARS = list(range(2004, 2027))
PAGES = list(range(1, 11))
MAX_WORKERS = 12

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


# Build a reverse lookup: keyword (lowercase) -> main_term
TERM_TO_MAIN = {}
for main_term, synonyms in SEARCH_TERMS.items():
    TERM_TO_MAIN[main_term.lower()] = main_term
    for synonym in synonyms:
        TERM_TO_MAIN[synonym.lower()] = main_term

LOG_FILE = "scraper_progress.log"
OUTPUT_CSV = "news_combined_unique_parallel.csv"

# ==== Helpers ====
def get_next_key():
    global keys_exhausted_warned
    available = [i for i, count in enumerate(key_usage) if count < MAX_REQUESTS_PER_KEY]
    if not available:
        if not keys_exhausted_warned:
            print("All API keys exhausted. Remaining queued news tasks will be skipped.")
            keys_exhausted_warned = True
        return None
    idx = random.choice(available)
    key_usage[idx] += 1
    return API_KEYS[idx]

def fetch_gnews(term, year, page):
    key = get_next_key()
    if not key:
        return []
    query = urllib.parse.quote_plus(term.lower())
    url = (
        f"https://gnews.io/api/v4/search?"
        f"q={query}&from={year}-01-01&to={year}-12-31"
        f"&lang=en&token={key}&max=10&page={page}"
    )
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            return []
        articles = response.json().get("articles", [])
        results = []
        for a in articles:
            pub_date = a["publishedAt"][:10]
            url_link = a["url"]
            title = a["title"]
            results.append((pub_date, term, title, url_link))
        return results
    except Exception as e:
        print(f"GNews error: {e}")
        return []

def fetch_google_news_html(term, year, page):
    query = urllib.parse.quote_plus(f'"{term.lower()}"')
    start = (page - 1) * 10
    url = (
        f"https://www.google.com/search?q={query}"
        f"&tbm=nws&tbs=cdr:1,cd_min:1/1/{year},cd_max:12/31/{year}&start={start}"
    )
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for g in soup.select(".dbsr"):
            title_tag = g.select_one("div.JheGif.nDgy9d")
            link_tag = g.a["href"] if g.a else ""
            date_tag = g.select_one("span.WG9SHc > span")
            if title_tag and link_tag and date_tag:
                title = title_tag.get_text(strip=True)
                raw_date = date_tag.get_text(strip=True)
                pub_date = try_parse_date(raw_date, fallback_year=year)
                results.append((pub_date, term, title, link_tag))
        return results
    except Exception as e:
        print(f"Google HTML error: {e}")
        return []

def try_parse_date(raw_date, fallback_year=None):
    try:
        dt = date_parser.parse(raw_date, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        if fallback_year:
            return f"{fallback_year}-01-01"
        else:
            return "Unknown"

def normalize_date_to_month(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m")
    except Exception:
        return "Unknown"

def month_in_range(month_str, start_month=START_MONTH, end_month=END_MONTH):
    if month_str == "Unknown":
        return False
    return start_month <= month_str <= end_month

def load_log():
    return set(open(LOG_FILE).read().splitlines()) if os.path.exists(LOG_FILE) else set()

def save_log(entry):
    with open(LOG_FILE, "a") as f:
        f.write(entry + "\n")

def save_to_csv(data, filename=OUTPUT_CSV):
    file_exists = os.path.exists(filename)
    with open(filename, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Month", "Main_Search_Term", "Title", "URL", "NoM"])
        writer.writerows(data)

# ==== Main Runner Parallel ====
def scrape_task(task):
    keyword_lower, year, page = task
    main_term = TERM_TO_MAIN.get(keyword_lower, keyword_lower)
    collected = []
    seen_urls = set()

    for r in fetch_gnews(keyword_lower, year, page):
        month = normalize_date_to_month(r[0])
        if not month_in_range(month):
            continue
        key = r[3].lower().strip()
        if key not in seen_urls:
            seen_urls.add(key)
            collected.append((month, main_term, r[2], r[3]))

    for r in fetch_google_news_html(keyword_lower, year, page):
        month = normalize_date_to_month(r[0])
        if not month_in_range(month):
            continue
        key = r[3].lower().strip()
        if key not in seen_urls:
            seen_urls.add(key)
            collected.append((month, main_term, r[2], r[3]))

    return task, collected

def run_scraper_parallel():
    completed = load_log()
    tasks = []

    for year in YEARS:
        for term, synonyms in SEARCH_TERMS.items():
            for keyword in [term] + synonyms:
                keyword_lower = keyword.lower()
                for page in PAGES:
                    task_id = f"{keyword_lower}|{year}|{page}"
                    if task_id not in completed:
                        tasks.append((keyword_lower, year, page))

    print(f"🚀 Total tasks: {len(tasks)}")

    seen_global = set()
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scrape_task, task): task for task in tasks}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Scraping"):
            task, collected = future.result()

            keyword_lower, year, page = task
            for month, main_term, title, url in collected:
                key = url.lower().strip()
                if key not in seen_global:
                    seen_global.add(key)
                    results.append((month, main_term, title, url, 1))  # NoM=1 per unique article

            save_log(f"{keyword_lower}|{year}|{page}")

    save_to_csv(results)

    return results

# ==== Run ====
if __name__ == "__main__":
    run_scraper_parallel()
    print(f"✅ Done! Saved with parallel speedup.")