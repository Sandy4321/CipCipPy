#    CipCipPy - Twitter IR system for the TREC Microblog track.
#    Copyright (C) <2011-2015>  Giacomo Berardi, Andrea Esuli, Diego Marcheggiani
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
CipCipPy

Real-time filtering package.
"""


__version__ = "0.2"
__authors__ = ["Giacomo Berardi <giacomo.berardi@isti.cnr.it>",
               "Andrea Esuli <andrea.esuli@isti.cnr.it>",
               "Diego Marcheggiani <diego.marcheggiani@isti.cnr.it>"]

import cPickle, os
#import time

from ..classification.feature import *
from ..classification.__init__ import TrainingSet
from ..utils import retweetRE, textHash
from ..utils.io import dataset_iter


class Filterer:

    def setFeatureExtractor(self, statusFeatEx, genericFeatEx, entityFeatEx, minLinkProb, expansion_limit = 0):
        self.statusFeatEx = FeatureExtractor(statusFeatEx)
        self.genericFeatEx = FeatureExtractor(genericFeatEx)
        self.entityFeatEx = FeatureExtractor(entityFeatEx)
        self.expansion_limit = expansion_limit
        self.minLinkProb = minLinkProb

    def featureExtract(self, tweet, external=True):
        """Extracts all the features from a sample"""
        features = []
        if tweet[1]:  # status
            features.extend(self.statusFeatEx.get(tweet[1]))
        if tweet[2]:  # segmented hashtag
            features.extend(self.genericFeatEx.get(tweet[2]))
        if external and tweet[3]:  # link title
            features.extend(self.genericFeatEx.get(tweet[3]))
        if external and tweet[4]:  # status annotaions
            features.extend(self.entityFeatEx.get((tweet[4], self.minLinkProb, self.expansion_limit)))
        if external and tweet[5]:  # link title annotation
            features.extend(self.entityFeatEx.get((tweet[5], self.minLinkProb, self.expansion_limit)))
        return features

    def featureExtractQuery(self, text, annotations, external=True):
        """Extracts all the features from a query"""
        features = []
        if text:  # topic
            features.extend(self.genericFeatEx.get(text))
        if external and annotations:  # annotations
            features.extend(self.entityFeatEx.get((annotations, self.minLinkProb, self.expansion_limit)))
        return features

    def intersect(self, query, text):
        """How many terms query amd text have in common."""
        return len(set(terms(query)) & set(terms(text)))

    def tweetHash(self, tweet):
        return textHash(str(tweet))


class SupervisedFilterer(Filterer):

    def __init__(self, classifier):
        self.classifier = classifier

    def get(self, queries, queriesAnnotated, neg, datasetPath, qrels, external, dumpsPath = None):
        """ Return filtered tweets for query topics and the relative time ranges.
        queries - queries from a topic file
        queriesAnnotated - queries from a topic file with annotated topics
        neg - number of negative samples (used only for idf computation with Rocchio)
        trainingSetPath - training set dir
        filteringIdsPath - path of ids and content per query (test set) for realtime filtering.
                           The tweet line format is defined in the method featureExtract
        qrels - relevance judgements
        external - True for using external information, otherwise False
        minLinkProb - minimum link probability for an annotation to be selected as feature
        dumpsPath - path where to store serialized results
        """
        results = {}
        printOut = {}
        for i, q in enumerate(queries):
            #alreadySeen = set()
            if int(q[0][2:]) not in qrels:
                continue
            #start_time = time.time()
            results[q[0]] = []
            negCount = neg
            testset_iter = dataset_iter(datasetPath, q.tweettime, q.newesttime)
            rawTweets=[]
            # Add the query as positive example
            query_annotations = queriesAnnotated[q[0]]
            features = self.featureExtractQuery(q[1], query_annotations, external)
            initialFeatures = set(self.featureExtractQuery(q[1], [], external))
            #positives = [q[1]]
            #print '[Debug]', 'QUERY', features
            rawTweets.append((q[0], True, features))
            # Add the first tweet as positive example
            for tweet in testset_iter:
                #alreadySeen.add(self.tweetHash(text))
                results[q[0]].append((str(tweet[0]), '1.0\tyes'))
                assert(tweet[0]==q.tweettime)
                features = self.featureExtract(tweet, external)
                #positives.append(tweet)
                #print '[Debug]', 'FIRST', features, features_binary
                rawTweets.append((tweet[0], True, features))
                break
            for tweet in dataset_iter(datasetPath, -float("inf"), q.tweettime-1, reverse=True):
                if negCount < 1:
                    break
                features = self.featureExtract(tweet, external)
                rawTweets.append((tweet[0], False, features))
                negCount -= 1
            # Add a negative sample at the axis origin
            # rawTweets.append((0, False, [], []))
            training = TrainingSet(rawTweets, 0)
            if rawTweets:
                training.vectorize()
                self.classifier.retrain(training.matrix, training.tweetTarget)
            ###tp, fp, fn = [], [], []
            for tweet in testset_iter:
                #currTweetHash = self.tweetHash(text)
                # exclude retweets
                tweetId = str(tweet[0])
                #TODO move this in dataset generation
                if retweetRE.findall(tweet[1]):# or currTweetHash in alreadySeen or viaUserRE.findall(text.split('\t\t')[0]):
                    continue
                #alreadySeen.add(currTweetHash)
                features = self.featureExtract(tweet, external)
                #features = self.cutOnLinkProb(features, self.minLinkProb)
                #features_binary = self.featureExtractBinary(text, external)
                #features_binary = self.cutOnLinkProb(features_binary, self.minLinkProb)
                if not features or not (len(initialFeatures & set(features))) or not hasUrl(tweet[1]):
                    continue
                test = training.vectorizeTest((tweet[0], False, features))
                classification = self.classifier.classify(test)
                #if classification == 1 and tweetId not in qrels[int(q[0][2:])][0]:
                    #fp.append(tweet)
                #if classification == 0 and tweetId in qrels[int(q[0][2:])][0]:
                    #fn.append(tweet)
                    #print '[Debug]', tweetId, features, features_binary, 'C ' + str(classification), \
                    #    'Target '+str(tweetId in qrels[int(q[0][2:])][0])
                #if classification == 1 and tweetId in qrels[int(q[0][2:])][0]:
                    #tp.append(tweet)
                    #print '[Debug]', 'POSITIVE', tweetId, features
                if classification == 1:
                    score = self.classifier.getProb(test) if callable(getattr(self.classifier, "getProb", None)) else 1.
                    results[q[0]].append((tweetId, str(score) + '\tyes'))
                    if tweetId in qrels[int(q[0][2:])][0]:
                        training.addExample((tweet[0], True, features))
                        # TODO pop an old positive sample?
                        training.vectorize()
                        self.classifier.retrain(training.matrix, training.tweetTarget)
                    #elif tweetId in qrels[int(q[0][2:])][1]:
                    else:
                        training.addExample((tweet[0], False, features))
                        training.vectorize()
                        self.classifier.retrain(training.matrix, training.tweetTarget)
            #print '[Debug] Query processed in ', time.time() - start_time, 'seconds.'
            #printOut[q[0]] = (positives, tp, fp, fn)
            if dumpsPath:
                cPickle.dump(results[q[0]], open(os.path.join(dumpsPath, q[0]), 'w'))
        return results, printOut
