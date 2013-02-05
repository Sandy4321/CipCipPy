# CipCipPy
# Twitter IR system for the TREC Microblog track.
#
# Authors: Giacomo Berardi <giacomo.berardi@isti.cnr.it>
#          Andrea Esuli <andrea.esuli@isti.cnr.it>
#          Diego Marcheggiani <diego.marcheggiani@isti.cnr.it>
# URL: <http://tag.isti.cnr.it/cipcippy/>
# For license information, see LICENSE

"""
CipCipPy

Real-time filtering package.
"""

__version__ = "0.1"
__authors__ = ["Giacomo Berardi <giacomo.berardi@isti.cnr.it>",
               "Andrea Esuli <andrea.esuli@isti.cnr.it>",
               "Diego Marcheggiani <diego.marcheggiani@isti.cnr.it>"]


from feature import *
import cPickle
from CipCipPy.classification.scikitNaiveBayes import TrainingSet, NBClassifier
import os

class Filterer:

    def cleanUtf(self, features):
        """Remove badly encoded terms."""
        cleanedFeatures = []
        for feat in features:
            feat = feat.encode('ascii', 'replace')
            if feat:
                cleanedFeatures.append(feat)
        return cleanedFeatures

    def intersect(self, query, text):
        """How many terms query amd text have in common."""
        return len(set(terms(query)) & set(terms(text)))

    def get(self, queries, n, m, rulesCount, trainingSetPath, filteringIdsPath, qrels, external, dumpsPath = None):
        """ Return filtered tweets for query topics and the relative time ranges.
        queries - queries from a topic file
        n - number of positive samples
        m - number of negative samples
        rulesCount - number of positive samples to find before starting classification
        trainingSetPath - training set dir
        filteringIdsPath - path of ids and content per query (test set) for realtime filtering
        qrels - relevance judgements
        external - True for using external information, otherwise False
        dumpsPath - path where to store serialized results
        """
        results = {}
        for q in queries:
            currRulesCount = rulesCount
            print currRulesCount, n, m, q
            results[q[0]] = []
            training = cPickle.load(open(os.path.join(trainingSetPath, q[0])))
            # (positives, negatives) ordered by relevance
            # ((tweetId, [features..]), (tweetId, [features..]), ..], [(tweetId, [features..]), ...])
            rawTweets=[]
            for tweetId, features in reversed(training[0][:n]):
                rawTweets.append((tweetId, True, self.cleanUtf(features)))
            for tweetId, features in training[1][:m]:
                rawTweets.append((tweetId, False, self.cleanUtf(features)))
            classifier = None
            training = TrainingSet(rawTweets, n)
            if rawTweets:
                training.countVectorize()
                classifier=NBClassifier(training.vectorcounts, training.tweetTarget)
            # do not train the first tweet
            firstTweet = True
            for line in open(os.path.join(filteringIdsPath, q[0])):
                tweetId, null, text = line.partition('\t\t')
                if currRulesCount > 0:
                    if self.intersect(q[1], text):
                        results[q[0]].append((tweetId, '0.5\tyes'))
                        if firstTweet:
                            firstTweet = False
                            continue
                        features = self.cleanUtf(featureExtractText(text[:-1], q[1], external))
                        if tweetId in qrels[int(q[0][2:])][0]:
                            training.addExample((tweetId, True, features))
                            currRulesCount -= 1
                        else:
                            training.addExample((tweetId, False, features))
                    continue
                elif currRulesCount == 0:
                    training.countVectorize()
                    if classifier:
                        classifier.retrain(training.vectorcounts, training.tweetTarget)
                    else:
                        classifier=NBClassifier(training.vectorcounts, training.tweetTarget)
                    currRulesCount = -1
                features = self.cleanUtf(featureExtractText(text[:-1], q[1], external))
                if not features:
                    continue
                #nb.test(tweetId, features)
                test=training.vectorizeTest((tweetId,False,features))
                classification = classifier.classify(test)
                #print tweetId, features, 'C' + str(classification[0])
                #print classifier.getProb(test)
                if classification[0] == 1:
                    results[q[0]].append((tweetId, str(classifier.getProb(test)[0][1]) + '\tyes'))
                    if firstTweet:
                        firstTweet = False
                        continue
                    if tweetId in qrels[int(q[0][2:])][0]:
                        training.addExample((tweetId, True, features))
                        # TODO pop a old positive sample? only if rules are not used?
                    else:
                        training.addExample((tweetId, False, features))
                    training.countVectorize()
                    classifier.retrain(training.vectorcounts, training.tweetTarget)
            if dumpsPath:
                cPickle.dump(results[q[0]], open(os.path.join(dumpsPath, q[0]), 'w'))
        return results