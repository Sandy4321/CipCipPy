"""Methods for extracting features (list of strings) from a text string."""

from inspect import isfunction
import nltk, math

from ..utils.hashtag import Segmenter
from ..utils import hashReplRE, urlRE, stopwords, punctuations, hashtagRE, replyRE, wordDotsRE


ANNOTATION_PREFIX = 'NMIS__aNn__'
URL_FEATURE = 'NMIS__UrL__'
HASHTAG_FEATURE = 'NMIS__Hashtag__'
MENTION_FEATURE = 'NMIS__Mention__'
ENTITY_FEATURE = 'NMIS__Entity__'
ALIAS_FEATURE = 'NMIS__Alias__'
ANNOTATION_EXPANSION_PREFIX = 'NMIS__aNnEXP__'
STEM_PREFIX = 'NMIS__Stem__'

class FeatureExtractor:
    """Concatenate feature extraction functions"""

    def __init__(self, functions):
        self.functions = functions

    def get(self, data):
        result = []
        for f in self.functions:
            if isfunction(f):
                if isinstance(data, basestring):
                    result.extend(f(data))
                else:
                    result.extend(f(*data))
        return result

filterSet = stopwords #| punctuations

punctuations2 = set(('\'', '"', '`')) | punctuations

#FIXME optimize singleton generators, redundant code
segmenter = None
def getSegmenter(dictionary):
    global segmenter
    if not segmenter:
        segmenter = Segmenter(dictionary)
    return segmenter

stemmer = None
def getStemmer():
    global stemmer
    if not stemmer:
        stemmer = nltk.stem.LancasterStemmer()
    return stemmer

lemmatizer = None
def getLemmatizer():
    global lemmatizer
    if not lemmatizer:
        lemmatizer = nltk.stem.WordNetLemmatizer()
    return lemmatizer

def surfaceForms(data, min_linkprob, min_score):
    """Returns the surface forms of all the entities of each mention in the text (Exp3 in the SAC 2015 paper)"""
    if min_linkprob > 1. or min_score > 1. or not data:
        return []
    spots = data[0]
    mentions = data[1]
    result = []
    # Add the spots in the text to the final result
    partial_result = set()
    # Explore other mentions
    for spot in (s for s in spots if s["linkProbability"] >= min_linkprob):
        base_linkprob = spot["linkProbability"]
        partial_result.add(spot["mention"].replace(" ", "_"))
        for entity in spot["candidates"]:
            ent_id = entity["entity"]
            ent_id_str = str(ent_id)
            if ent_id_str not in mentions:
                continue
            ent_comm = entity["commonness"]
            curr_mentions = []
            for mention in (m for m in mentions[ent_id_str] if m["linkProbability"] >= min_linkprob
                            and m["linkFrequency"] > 2 and m["mention"] != spot["mention"]):
                ment_ent_comm = 0
                for ment_ent in mention["candidates"]:
                    if ment_ent["entity"] == ent_id:
                        ment_ent_comm = ment_ent["commonness"]
                        break
                curr_mentions.append((mention["mention"], mention["linkProbability"] * ment_ent_comm
                                      * ent_comm * base_linkprob))
            result.extend(curr_mentions)
    result = [r for r in result if r[1] >= min_score]
    if not result:
        return [ALIAS_FEATURE + feat for feat in partial_result]
    result = zip(*result)[0]
    result = set(r.replace(" ", "_") for r in result)
    return [ALIAS_FEATURE + feat for feat in result.union(partial_result)]

def firstEntity(data, min_linkprob, min_score):
    """Returns only the first candidate entity for each mention"""
    if min_linkprob > 1. or not data:
        return []
    spots = data[0]
    result = []
    for spot in (s for s in spots if s["linkProbability"] >= min_linkprob):
        if not spot["candidates"]:
            continue
        candidate = max((entity["commonness"], entity["entity"]) for entity in spot["candidates"])[1]
        result.append(ENTITY_FEATURE + str(candidate))
    return result

def mentionsInText(data, min_linkprob, min_score):
    """Returns the mentions spotted in the text (Exp1 in the SAC 2015 paper)"""
    if min_linkprob > 1. or not data:
        return []
    spots = data[0]
    result = []
    # Explore mentions
    for spot in (s for s in spots if s["linkProbability"] >= min_linkprob):
        result.append(MENTION_FEATURE + spot["mention"].replace(" ", "_"))
    return result

def candidateEntities(data, min_linkprob, min_score):
    """Returns all the candidate entities for each mention (Exp2 in the SAC 2015 paper)"""
    if min_linkprob > 1. or min_score > 1. or not data:
        return []
    spots = data[0]
    mentions = data[1]
    result = []
    # Explore mentions
    for spot in (s for s in spots if s["linkProbability"] >= min_linkprob):
        base_linkprob = spot["linkProbability"]
        for entity in spot["candidates"]:
            if (entity["commonness"] * base_linkprob) >= min_score:
                result.append(ENTITY_FEATURE + str(entity["entity"]))
    return result

def allEntityFeatures(data, min_linkprob, min_score):
    return candidateEntities(data, min_linkprob, min_score) + surfaceForms(data, min_linkprob, min_score)

def terms(text):
    """Returns the unique, filtered, terms of a text"""
    terms = []
    text = hashReplRE.sub(" ", text)
    text = urlRE.sub(" ", text)
    text = wordDotsRE.sub(".", text)
    for sent in nltk.sent_tokenize(text):
        for subSent in sent.split(';'):
            terms.extend(nltk.word_tokenize(subSent))
    terms = [t.lower() for t in terms if t.strip() and len(t) > 1 and t != u'\ufffd']
    return [t for t in terms if t not in filterSet and not set(t).issubset(punctuations2)]

def lemmas(text):
    text_terms = terms(text)
    return [getLemmatizer().lemmatize(t) for t in text_terms]

def stems(text):
    text_terms = terms(text)
    return [STEM_PREFIX + getStemmer().stem(t) for t in text_terms]

def bigrams(text):
    """Returns term pairs of a text"""
    bigrams_list = []
    text = hashReplRE.sub(";", text)
    text = urlRE.sub(";", text)
    text = wordDotsRE.sub(".", text)
    for sent in nltk.sent_tokenize(text):
        for subSent in sent.split(';'):
            bigrams_list.extend(nltk.bigrams(nltk.word_tokenize(subSent)))
    # Differently from terms, we accept stopwords in bigrams
    return ['_'.join(b).lower() for b in bigrams_list if u'\ufffd' not in b #and len(b[0]) > 1 and len(b[1]) > 1
                    and not set(b[0]).issubset(punctuations2) and not set(b[1]).issubset(punctuations2)]

def hashtags(text):
    """Returns hashtags of a text"""
    return [h for h in hashtagRE.findall(text)]

def mentions(text):
    """Returns mentioned users of a text"""
    return [r for r in replyRE.findall(text)]

def hasHashtags(text):
    """Returns hashtags of a text"""
    return [HASHTAG_FEATURE] if hashtagRE.findall(text) else []

def hasMentions(text):
    """Returns mentioned users of a text"""
    return [MENTION_FEATURE] if replyRE.findall(text) else []

def hasUrl(text):
    """Return a feature if there is a url in the text"""
    return [URL_FEATURE] if urlRE.findall(text) else []

def segmHashtags(text, dictionary):
    """Returns terms of the segmented hashtags of a text"""
    segmenter = getSegmenter(dictionary)
    return terms(' '.join(' '.join(segmenter.get(ht)[0]) for ht in hashtags(text)))

def segmHashtagsBigrams(text, dictionary):
    """Returns term pairs of the segmented hashtags of a text"""
    segmenter = getSegmenter(dictionary)
    hashBigr = []
    for ht in hashtags(text):
        hashBigr.extend(bigrams(' '.join(segmenter.get(ht)[0])))
    return hashBigr

def countIntersectingTerms(text, query):
    """Returns a feature representing the number of terms in common between two texts"""
    result=[]
    termsQuery=terms(query)
    termsText=terms(text)
    intersectionNumber = len(set(termsQuery) & set(termsText))
    normalizedIntersection=math.floor((float(intersectionNumber)/float(len(termsQuery)))*5.0)
    for i in range(int(normalizedIntersection)):
        result.append('_intersect_')
    return result

def annotations(annotationTweet):
    return [ANNOTATION_PREFIX + a for a in annotationTweet.split('\t')]

