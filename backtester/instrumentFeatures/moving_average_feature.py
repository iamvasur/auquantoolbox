from instrument_feature import InstrumentFeature
from backtester.financial_fn import ma

class MovingAverageInstrumentFeature(InstrumentFeature):

    @classmethod
    def validateInputs(cls, featureParams, featureKey, currentFeatures, instrument):
        return True

    @classmethod
    def compute(cls, featureParams, featureKey, currentFeatures, instrument):
        data = instrument.getLookbackFeatures().getData()[featureParams['featureName']]
        avg = ma(data, featureParams['period'])
        if len(avg.index) > 0 :
        	return avg[-1]
        else:
        	return currentFeatures[featureParams['featureName']]
        