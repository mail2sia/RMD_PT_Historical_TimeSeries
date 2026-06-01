import os
import csv
import time
import random
import requests
import pandas as pd
import threading
from urllib.parse import quote_plus
from tqdm import tqdm
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ==== Country Code Mapping ====
COUNTRY_MAPPING = {
    "united states": "US", "usa": "US", "america": "US", "american": "US",
    "china": "CN", "chinese": "CN", "peoples republic": "CN",
    "japan": "JP", "japanese": "JP", "india": "IN", "indian": "IN",
    "germany": "DE", "deutsch": "DE", "german": "DE", "france": "FR", "french": "FR",
    "united kingdom": "UK", "britain": "UK", "british": "UK", "england": "UK",
    "canada": "CA", "canadian": "CA", "australia": "AU", "australian": "AU",
    "brazil": "BR", "brazilian": "BR", "mexico": "MX", "mexican": "MX",
    "russia": "RU", "russian": "RU", "south korea": "KR", "korea": "KR", "korean": "KR",
    "indonesia": "ID", "indonesian": "ID", "philippines": "PH", "philippine": "PH",
    "thailand": "TH", "thai": "TH", "vietnam": "VI", "vietnamese": "VI",
    "singapore": "SG", "singaporean": "SG", "malaysia": "MY", "malaysian": "MY",
    "pakistan": "PK", "pakistani": "PK", "bangladesh": "BD", "bangladeshi": "BD",
    "spain": "ES", "spanish": "ES", "italy": "IT", "italian": "IT",
    "netherlands": "NL", "dutch": "NL", "belgium": "BE", "belgian": "BE",
    "switzerland": "CH", "swiss": "CH", "sweden": "SE", "swedish": "SE",
    "norway": "NO", "norwegian": "NO", "denmark": "DK", "danish": "DK",
    "finland": "FI", "finnish": "FI", "poland": "PL", "polish": "PL",
    "turkey": "TR", "turkish": "TR", "iran": "IR", "iranian": "IR",
    "egypt": "EG", "egyptian": "EG", "south africa": "ZA", "african": "ZA",
    "argentina": "AR", "argentinian": "AR", "chile": "CL", "chilean": "CL",
    "colombia": "CO", "colombian": "CO", "peru": "PE", "peruvian": "PE",
    "israel": "IL", "israeli": "IL", "new zealand": "NZ", "zealand": "NZ",
    "greece": "GR", "greek": "GR", "austria": "AT", "austrian": "AT",
    "portugal": "PT", "portuguese": "PT", "ireland": "IE", "irish": "IE",
    "cyprus": "CY", "cypriot": "CY", "romania": "RO", "romanian": "RO",
    "bulgaria": "BG", "bulgarian": "BG", "ukraine": "UA", "ukrainian": "UA",
    "hungary": "HU", "hungarian": "HU", "czech": "CZ", "czechoslovak": "CZ",
    "saudi arabia": "SA", "saudi": "SA", "united arab emirates": "AE", "emirates": "AE",
    "kuwait": "KU", "kuwaiti": "KU", "qatar": "QA", "qatari": "QA",
    "morocco": "MA", "moroccan": "MA", "algeria": "DZ", "algerian": "DZ",
    "nigeria": "NG", "nigerian": "NG", "kenya": "KE", "kenyan": "KE",
    "ghana": "GH", "ghanaian": "GH", "tanzania": "TA", "tanzanian": "TA",
    "uganda": "UG", "ugandan": "UG", "ethiopia": "ET", "ethiopian": "ET",
}

URL_COUNTRY_MAP = {
    ".us/": "US", ".com/": "US", ".uk/": "UK", ".co.uk/": "UK",
    ".cn/": "CN", ".com.cn/": "CN", ".jp/": "JP", ".co.jp/": "JP",
    ".de/": "DE", ".com.de/": "DE", ".fr/": "FR", ".com.fr/": "FR",
    ".ca/": "CA", ".au/": "AU", ".br/": "BR", ".com.br/": "BR",
    ".mx/": "MX", ".com.mx/": "MX", ".ru/": "RU", ".kr/": "KR", ".co.kr/": "KR",
    ".id/": "ID", ".co.id/": "ID", ".ph/": "PH", ".com.ph/": "PH",
    ".th/": "TH", ".co.th/": "TH", ".vn/": "VI", ".sg/": "SG", ".com.sg/": "SG",
    ".my/": "MY", ".com.my/": "MY", ".pk/": "PK", ".com.pk/": "PK",
    ".bd/": "BD", ".com.bd/": "BD", ".es/": "ES", ".com.es/": "ES",
    ".it/": "IT", ".com.it/": "IT", ".nl/": "NL", ".be/": "BE", ".ch/": "CH",
    ".se/": "SE", ".no/": "NO", ".dk/": "DK", ".fi/": "FI", ".pl/": "PL",
    ".tr/": "TR", ".com.tr/": "TR", ".ir/": "IR", ".eg/": "EG", ".za/": "ZA",
    ".ar/": "AR", ".com.ar/": "AR", ".cl/": "CL", ".com.cl/": "CL",
    ".co/": "CO", ".com.co/": "CO", ".pe/": "PE", ".com.pe/": "PE",
    ".il/": "IL", ".nz/": "NZ", ".gr/": "GR", ".at/": "AT",
    ".pt/": "PT", ".ie/": "IE", ".cy/": "CY", ".ro/": "RO", ".bg/": "BG",
    ".ua/": "UA", ".hu/": "HU", ".cz/": "CZ", ".sa/": "SA", ".com.sa/": "SA", ".ae/": "AE",
}

# ==== CONFIG ====

API_KEYS = [
    "556914b73d45d537222c67e536c9c276", "6f1faa3087ebd3e79b1bb29d886d862d",
    "9154e3a1b915ec4c2ad8b9b526cd265d", "6be276469ff1d608ec5bb22c821f9b2c",
    "73316fa5cee173dec407e6fd13d5493d", "3a10bd1f5e44b1e5d5d928c172d50f21",
    "51c713e97fdef85405856d0c67900d1b", "b87047ebef28b088105cc0b0400800bc",
    "18f6dd68a40887fb6ad7fd95f17916e5", "81246f8e958d829ff46388e1325efc66"
]


MAX_REQUESTS_PER_KEY = 25000
key_usage = [0] * len(API_KEYS)
api_keys_exhausted = False
api_keys_exhausted_lock = threading.Lock()

START_YEAR = 2004
END_YEAR = 2026

OUTPUT_FILE = "funding_data_gnews_2004_2026.csv"
CACHE_FILE = "funding_gnews_cache_2004_2026.txt"
MAX_RESULTS = 100
MAX_WORKERS = 10  # Increased from 3 for better parallelization
API_RATE_LIMIT = 5  # Increased from 1 - allow 5 concurrent API calls
REQUEST_DELAY = 0.05  # Reduced from 0.5 - GNews API can handle faster requests

semaphore = threading.Semaphore(API_RATE_LIMIT)
request_lock = threading.Lock()

SEARCH_TERMS = {
    "Digital Health Tools": ["Mobile Health Apps"],
    "Virtual Reality Exposure Therapy": ["VR Exposure Therapy"],
    "Brain Stimulation Technologies": ["Neurostimulation Techniques"],
    "Eye Movement Desensitization and Reprocessing": ["EMDR Therapy"],
    "Cognitive Technologies": ["Cognitive Aids"],
    "Electroencephalography": ["EEG"],
    "Transcranial Magnetic Stimulation": ["Repetitive Transcranial Magnetic Stimulation"],
    "Brain-Computer Interface": ["Direct Neural Interface"],
    "Augmentative Communication Devices": ["Speech Generating Devices"],
    "Neurofeedback Systems": ["EEG Biofeedback Therapy"],
    "Biofeedback Devices": ["Physiological Monitoring Tools"],
    "Metaverse": ["Immersive Virtual Environments"],
    "Genetic Testing": ["Genetic Screening"],
    "Personalized Medicine": ["Precision Medicine"],
    "Neuromodulation Techniques": ["Vagus Nerve Stimulation"],
    "Resting-state Functional Magnetic Resonance Imaging": ["rs-fMRI"],
    "Voxel-based Lesion-Symptom Mapping": ["Voxel-Based Symptom-Lesion Mapping"],
    "Neuroplasticity Techniques": ["Cognitive Rehabilitation"],
    "Blockchain for Data Protection": ["Decentralized Data Security"],
    "Privacy-Preserving AI in Digital Mental Health": ["Federated Learning"],
    "Secure Data Storage for Patient Records": ["HIPAA-Compliant Cloud Storage"],
    "Smart Wearable Mental Health Trackers": ["AI-Powered Wearables"],
    "Digital Imaging Technologies for Brain Scanning": ["Neuroimaging AI"],
    "Cognitive Behavioral Therapy": ["Psychotherapeutic Treatment"],
    "Dialectical Behavior Therapy": ["Emotional Regulation Therapy"],
    "Trauma-Focused CBT": ["TF-CBT"],
    "Exposure Therapy": ["Systematic Desensitization"],
    "Mindfulness-Based Stress Reduction": ["Mindfulness-Based Cognitive Therapy"],
    "Interpersonal Psychotherapy": ["Dynamic Interpersonal Therapy"],
    "Reality Testing Techniques": ["Cognitive Reality Checking"],
    "Psychoeducation Programs": ["Mental Health Awareness Training"],
    "Neurocognitive Training": ["Cognitive Enhancement Exercises"],
    "Antipsychotic Medications": ["Neuroleptics"],
    "Selective Serotonin Reuptake Inhibitors": ["SSRIs"],
    "Benzodiazepines": ["Anxiolytics"],
    "Mood Stabilizers": ["Lithium"],
    "Antidepressants": ["MAOIs"],
    "Neuroprotective Agents": ["Cognitive Enhancers"],
    "Meditation and Relaxation Techniques": ["Mindfulness Meditation"],
    "Creative Arts Therapies": ["Music Therapy"],
    "Expressive Writing & Journaling": ["Therapeutic Writing"],
    "Animal-Assisted Interventions": ["Therapy Animals"],
    "Dietary Interventions & Supplements": ["Nutritional Psychiatry"],
    "Traditional & Alternative Medicine Approaches": ["Ayurveda"],
    "Memory Retrieval Techniques": ["Cognitive Recall Training"],
    "Cognitive Enhancement Programs": ["Neuroplasticity Exercises"],
    "Social Skills Training": ["Interpersonal Effectiveness Training"],
    "Emotion Regulation Training": ["DBT Emotion Skills"],
    "Behavioral Activation Therapy": ["BAT"],
    "Peer Support Programs & Online Communities": ["Mental Health Peer Networks"],
    "Stem Cell Therapy for Neurological Disorders": ["Regenerative Medicine"],
    "Regenerative Medicine Approaches": ["Tissue Engineering"],
    "Neurobiological Assessments for Mental Disorders": ["Brain Function Testing"],
    "Sleep Pattern Monitoring & Manipulation": ["Sleep Hygiene Coaching"],
    "Psychophysiological Metrics for Treatment Response": ["Heart Rate Variability"],
    # Common Mental Diseases
    "Major Depressive Disorder": ["Clinical Depression", "Unipolar Depression"],
    "Generalized Anxiety Disorder": ["GAD"],
    "Bipolar Disorder": ["Manic Depression", "Bipolar Affective Disorder"],
    "Schizophrenia": ["Psychotic Disorder"],
    "Post-Traumatic Stress Disorder": ["PTSD", "Combat Stress"],
    "Obsessive-Compulsive Disorder": ["OCD"],
    "Attention-Deficit Hyperactivity Disorder": ["ADHD", "ADD"],
    "Autism Spectrum Disorder": ["ASD", "Autism"],
    "Borderline Personality Disorder": ["BPD", "Emotional Dysregulation"],
    "Panic Disorder": ["Panic Attacks"],
    "Social Anxiety Disorder": ["Social Phobia"],
    "Eating Disorders": ["Bulimia Nervosa", "Binge Eating Disorder"],
    "Substance Use Disorder": ["Addiction", "Drug Dependence"],
    "Seasonal Affective Disorder": ["SAD", "Winter Depression"],
    "Persistent Depressive Disorder": ["Dysthymia", "Chronic Depression"],
    "Agoraphobia": ["Fear of Open Spaces"],
    "Specific Phobia": ["Simple Phobia"],
    "Tourette Syndrome": ["Tourette's", "Tic Disorder"],
    "Dissociative Identity Disorder": ["Multiple Personality Disorder", "DID"],
    "Somatic Symptom Disorder": ["Somatization"],
    "Adjustment Disorder": ["Situational Depression"],
    "Hoarding Disorder": ["Compulsive Hoarding"],
    "Trichotillomania": ["Hair Pulling Disorder"],
    "Excoriation Disorder": ["Skin Picking Disorder", "Dermatillomania"],
    "Body Dysmorphic Disorder": ["BDD"],
    "Conduct Disorder": ["Oppositional Defiant Disorder"],
    "Separation Anxiety Disorder": [],
    "Premenstrual Dysphoric Disorder": ["PMDD"],
    "Gender Dysphoria": [],
    "Sleep Disorders": ["Insomnia", "Narcolepsy", "Sleep Apnea"],
    "Neurodevelopmental Disorders": ["Intellectual Disability", "Learning Disabilities"],
    # RMD - Rare Mental Disorders
    "Reactive Attachment": [],
    "Pyromania": ["Pathological Fire Setting"],
    "Othello": ["Morbid Jealousy", "Delusional Jealousy", "Pathological Jealousy"],
    "Disinhibited Social Engagement": ["Disinhibited Attachment"],
    "Schizoaffective": ["Schizo-affective Psychosis", "Schizo-affective Schizophrenia"],
    "Erotomanic": ["De Clérambault's", "Erotomania"],
    "Dementia pugilistica": ["Punch Drunk", "Chronic Traumatic Encephalopathy"],
    "Olfactory Reference": [],
    "Hypergraphia": [],
    "Wendigo Psychosis": ["Witiko Psychosis"],
    "Body Integrity Dysphoria": ["Body Integrity Identity", "Xenomelia", "Apotemnophilia"],
    "koro": ["genital retraction"],
    "Dissociative Fugue": ["Psychogenic Fugue", "Dissociative Amnesia with Fugue"],
    "Delusional": ["Paranoia"],
    "Anorexia nervosa": ["Anorexia"],
    "Impulse Control": ["Impulsivity"],
    "Postpartum Psychosis": ["Puerperal Psychosis", "Postnatal Psychosis"],
    "Savant": ["Savantism", "idiot savant"],
    "Brief Psychotic": ["Brief Reactive Psychosis", "Bouffée Délirante"],
    "Schizotypal Personality": ["Schizotypal"],
    "Selective Mutism": ["Situational Mutism"],
    "Kleine-Levin": ["Familial Hibernation", "Sleeping Beauty"],
    "Capgras": ["Delusion of Doubles"],
    "Narcissistic Personality": ["Grandiosity"],
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
    "Reduplicative Paramnesia": [],
    "Histrionic Personality": ["Dramatic Personality"],
    "Autosarcophagy": ["Self-Cannibalism"],
    "Ganser": ["hysterical pseudodementia", "prison psychosis"],
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
    "Childhood Disintegrative Disorder": ["Heller's", "Heller"]
}


# ==== UTILITIES ====

class APIKeysExhaustedError(RuntimeError):
    """Raised when all configured GNews API keys are exhausted."""


def save_to_csv(data_batch):
    file_exists = os.path.exists(OUTPUT_FILE)
    with open(OUTPUT_FILE, "a", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["date", "NoM", "search_term", "url"])
        writer.writerows(data_batch)

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def update_cache(task_key):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{task_key}\n")

def make_task_key(year, month, term):
    return f"{year}-{month:02d}-{term}"

def get_api_key():
    global key_usage, api_keys_exhausted
    for idx, usage in enumerate(key_usage):
        if usage < MAX_REQUESTS_PER_KEY:
            key_usage[idx] += 1
            return API_KEYS[idx]
    with api_keys_exhausted_lock:
        if not api_keys_exhausted:
            api_keys_exhausted = True
            print("All API keys exhausted. Remaining queued funding tasks will be skipped.")
    raise APIKeysExhaustedError("All API keys exhausted")

def search_gnews(task):
    year, month, term = task
    task_key = make_task_key(year, month, term)

    start_date = f"{year}-{month:02d}-01"
    end_day = "28" if month == 2 else "30"
    end_date = f"{year}-{month:02d}-{end_day}"

    query = f'"{term}" (funding OR investment OR grant)'
    url = (
        f"https://gnews.io/api/v4/search?q={quote_plus(query)}"
        f"&from={start_date}&to={end_date}"
        f"&lang=en&country=us&max={MAX_RESULTS}&apikey={get_api_key()}"
    )

    try:
        with semaphore:  # Semaphore moved here for better concurrency control
            time.sleep(REQUEST_DELAY)
            response = requests.get(url, timeout=30)
            if response.status_code == 429:  # Too many requests
                time.sleep(2)  # Wait longer on rate limit
                return task_key, []
            if response.status_code != 200:
                return task_key, []

            articles = response.json().get("articles", [])
            results = []

            for article in articles:
                article_url = article.get("url", "")
                published_at = article.get("publishedAt", "")
                
                # Extract country from source metadata
                source = article.get("source", {})
                country_name = source.get("name", "").lower()
                country = "UN"  # Unknown by default
                
                # Try to infer country from source name or URL
                if "united states" in country_name or "usa" in country_name or "us" in country_name:
                    country = "US"
                elif "united kingdom" in country_name or "uk" in country_name or "britain" in country_name:
                    country = "UK"
                elif "china" in country_name:
                    country = "CN"
                elif "japan" in country_name:
                    country = "JP"
                elif "germany" in country_name or "deutsch" in country_name:
                    country = "DE"
                elif "france" in country_name or "french" in country_name:
                    country = "FR"
                elif "canada" in country_name or "canadian" in country_name:
                    country = "CA"
                elif "australia" in country_name or "australian" in country_name:
                    country = "AU"
                elif "india" in country_name or "indian" in country_name:
                    country = "IN"
                elif article_url:
                    # Try to extract from URL domain
                    if ".us/" in article_url or ".com/" in article_url:
                        country = "US"
                    elif ".uk/" in article_url or ".co.uk/" in article_url:
                        country = "UK"
                    elif ".cn/" in article_url:
                        country = "CN"
                    elif ".jp/" in article_url:
                        country = "JP"
                    elif ".de/" in article_url:
                        country = "DE"
                    elif ".fr/" in article_url:
                        country = "FR"
                    elif ".ca/" in article_url:
                        country = "CA"
                    elif ".au/" in article_url or ".com.au/" in article_url:
                        country = "AU"
                    elif ".in/" in article_url:
                        country = "IN"

                if article_url and published_at:
                    try:
                        pub_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        normalized_date = pub_date.strftime("%Y-%m")
                    except Exception:
                        normalized_date = f"{year}-{month:02d}"

                    # Combine term and country with underscore
                    term_with_country = f"{term}_{country}"
                    results.append((normalized_date, 1, term_with_country, article_url))

    except APIKeysExhaustedError:
        # Exhaustion is reported once globally.
        return task_key, []
    except Exception as e:
        print(f"⚠️ Request Error: {term} {year}-{month}: {e}")
        return task_key, []

    return task_key, results

# ==== MAIN ====

def main():
    cache = load_cache()
    tasks = []

    for year in range(START_YEAR, END_YEAR + 1):
        max_month = 2 if year == END_YEAR else 12
        for main_term, synonyms in SEARCH_TERMS.items():
            full_terms = [main_term] + synonyms
            for term in full_terms:
                for month in range(1, max_month + 1):
                    task_key = make_task_key(year, month, term)
                    if task_key not in cache:
                        tasks.append((year, month, term))

    print(f"🚀 Tasks to run: {len(tasks)}")
    print(f"⚠️  Press Ctrl+C to stop gracefully")

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_task = {executor.submit(search_gnews, task): task for task in tasks}

            for future in tqdm(as_completed(future_to_task), total=len(future_to_task), desc="Querying GNews"):
                try:
                    task_key, results = future.result()
                    if results:
                        save_to_csv(results)
                    update_cache(task_key)
                except Exception as e:
                    print(f"❌ Error during scraping: {e}")

        print(f"✅ Finished! Data saved to {OUTPUT_FILE}")
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Interrupted by user. Progress has been saved.")
        print(f"💾 Data saved to {OUTPUT_FILE}")
        print(f"📝 Cache saved to {CACHE_FILE}")
        print(f"🔄 Run again to continue from where you left off.")

# ==== PREVIEW CSV ====

def preview_collected():
    if os.path.exists(OUTPUT_FILE):
        df = pd.read_csv(OUTPUT_FILE)
        print(df.tail(5))
    else:
        print("No data yet!")

if __name__ == "__main__":
    main()
