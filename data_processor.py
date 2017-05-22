import math
from datetime import timedelta
import numpy as np
import datascraper as ds
import option
import future
from constants import *
import useful_fn as utils
import time
import os
import order


def atm_vol(x, y, order):
    delta = 0.5
    if order == 2:
        p = np.polyfit(x, y, 1)
        atmvol = p[0] * delta + p[1]
    else:
        p = np.polyfit(x, y, 2)
        atmvol = p[0] * delta**2 + p[1] * delta + p[2]
    return atmvol


def shouldUpdateOption(opt, currentFutureVal):
    return (np.abs(opt.k - currentFutureVal) < 300)

def getContinuousSaveStateFilename():
    d = utils.convert_time(START_TIME).date()
    return CONTINUOS_SAVE_STATE_FILE_PREFIX + SAMPLE_OPTION_INSTRUMENT_PREFIX + '_' + str(d) + '.npy'


def getHistoryCsvFilename():
    d = utils.convert_time(START_TIME).date()
    return HISTORY_CSV_FILE_PREFIX + SAMPLE_OPTION_INSTRUMENT_PREFIX + '_' + str(d) + '.csv'


def straddle(opt_arr, s):
    lowS = int(math.floor(s / 100.0)) * 100
    highS = int(math.ceil(s / 100.0)) * 100
    lowSCallSymbol = SAMPLE_OPTION_INSTRUMENT_PREFIX + str(lowS) + '003'
    lowSPutSymbol = SAMPLE_OPTION_INSTRUMENT_PREFIX + str(lowS) + '004'
    highSCallSymbol = SAMPLE_OPTION_INSTRUMENT_PREFIX + str(highS) + '003'
    highSPutSymbol = SAMPLE_OPTION_INSTRUMENT_PREFIX + str(highS) + '004'
    std1 = opt_arr[lowSCallSymbol].price + opt_arr[lowSPutSymbol].price
    std2 = opt_arr[highSCallSymbol].price + opt_arr[highSPutSymbol].price
    d1 = opt_arr[lowSCallSymbol].delta + opt_arr[lowSPutSymbol].delta
    d2 = opt_arr[highSCallSymbol].delta + opt_arr[highSPutSymbol].delta
    return std1, std2, d1, d2


# optionsDict - dictionary of options with instrumentId as key, and value as option class
# marketData - dictionary 
# featureData - dictionary
# positionData - has delta, theta, gamma, total_options
# returns an array of dictionary of predictions. A prediction looks like this
# {instrumentId: 'OptionName',               name of option, or name of future
#  volume: 5,                                lots you need to buy or sell
#  type: 1}                               1 for BUY or -1 for SELL                            
def executePredictor(timeOfUpdate, future, optionsDict, marketData, featureData, positionData, threshold):
    # TODO CHADINI:
    futureVal =  future.getFutureVal()
    omega = 0.25
    
    curr_vol = marketData['Vol']
    pred = get_pred(marketData, featureData, omega)
    edge = pred - curr_vol

    long_lim = 500
    short_lim = -300
    predictions = settle_expiry(timeOfUpdate, optionsDict)
    if len(predictions) == 0:
        predictions = exit_position(timeOfUpdate, futureVal, optionsDict, marketData, featureData, positionData, edge, threshold)
    if len(predictions) == 0:
        predictions = enter_position(timeOfUpdate, futureVal, optionsDict, marketData, featureData, positionData, edge, threshold, long_lim, short_lim)

    return predictions

def get_pred(marketData, featureData, omega):
    
    Y_hat = 1.1 * featureData['HL AVol'] - 0.1 * marketData['R Vol'] #-0.25 * featureData['HL Rolling RVol'] + 0.25 * marketData['Rolling R Vol']#+ vcr_iv*(all_data['Future']/all_data['HL Future'] - 1)
    
    return Y_hat

def isExpiry(timeOfUpdate):
    convertedTime = utils.convert_time(timeOfUpdate)
    expiry = utils.convert_time(EXP_DATE)
    if  expiry - convertedTime < timedelta(minutes=2) :
        return True
    else:
        return False

def calc_retreat(positionData):
    return max(0.3, 0.2*np.abs(positionData['total_options'])/100.0)

def at_position_limit(positionData, long_lim, short_lim):
    if (positionData['total_options'] > long_lim) or (positionData['total_options'] < short_lim) :
        return True
    else:
        return False

def get_opt_ref(s):
    CallSymbol = SAMPLE_OPTION_INSTRUMENT_PREFIX + str(s) + '003'
    PutSymbol = SAMPLE_OPTION_INSTRUMENT_PREFIX + str(s) + '004'
    return CallSymbol, PutSymbol

def settle_expiry(timeOfUpdate, optionsDict):
 #EXPIRY: position goes to zero, no more trading
    predictions = []
    if  isExpiry(timeOfUpdate):
        for instrumentId in optionsDict:
            opt_position = optionsDict[instrumentId].position
            if (opt_position !=0):# if you should trade this option, change this
                prediction = {'instrumentId': instrumentId,
                          'volume': np.abs(opt.position),
                          'type': -np.sign(opt.position)}
                predictions.append(prediction)

    return predictions
def exit_condition(positionData, exit_threshold, edge):
    if (positionData['total_options'] < 0):
        if (-edge < exit_threshold) or (edge > 0):
            return True 
    elif (positionData['total_options'] > 0):
        if (edge < exit_threshold) or (edge < 0):             
            return True
    else:
        return False

def exit_position(timeOfUpdate, futureVal, optionsDict, marketData, featureData, positionData, edge, threshold):
    predictions = []
    if exit_condition(positionData, 0.2* threshold, edge):
        print('Getting out')
        for instrumentId in optionsDict:
            opt_position = optionsDict[instrumentId].position
            if (opt_position !=0):# if you should trade this option, change this
                prediction = {'instrumentId': instrumentId,
                          'volume': np.abs(opt.position),
                          'type': -np.sign(opt.position)}
                predictions.append(prediction)

    return predictions
        

def enter_position(timeOfUpdate, futureVal, optionsDict, marketData, featureData, positionData, edge, threshold, long_lim, short_lim):
    retreat = calc_retreat(positionData)
    if isExpiry(timeOfUpdate):
        print('Expiry, no trading')
        trade = False
    elif at_position_limit(positionData, long_lim, short_lim): #or (np.abs(edge) > (3*threshold)):
        print('Position Limit')
        trade = False
    elif np.abs(edge)>(threshold*(retreat)):
        print('Trading', edge,threshold*(retreat))
        trade = True
    else:
        print('Not Enough Edge',edge,threshold*(retreat) )
        trade = False

    predictions = []
    if trade:
        atm_call, atm_put = get_opt_ref(int(round(futureVal / 100.0, 0)) * 100)
        atm_options = [atm_call, atm_put]
        for instrumentId in atm_options:
            prediction = {'instrumentId': instrumentId,
                      'volume': 40,
                      'type': np.sign(edge)}
            predictions.append(prediction)

    return predictions

class UnderlyingProcessor:
    def __init__(self, futureVal, optionsData, startMarketData, startFeaturesData, startPositionData, startPnlData, startTime):
        self.histFutureInstruments = []  # for storing history of future instruments
        self.histOptionInstruments = {}  # for storing history of option instruments
        # secondsInterval = pd.date_range(start=START_DATE, end=END_DATE, freq='1S')
        # self.marketData = pd.DataFrame(index=secondsInterval, columns=['Future', 'Vol', 'Mkt_Straddle', 'Theo_Straddle'])

        self.marketData = [startMarketData]
        self.features = [startFeaturesData]
        self.lastTimeSaved = utils.convert_time(startTime)
        self.currentFuture = future.Future(futureVal, startTime)
        self.currentOptions = {}
        self.positionData = [startPositionData]
        self.pnlData = [startPnlData] # TODOKANAV: Put in constants
        for instrumentId in optionsData:
            optionData = optionsData[instrumentId]
            opt = option.Option(futurePrice=futureVal,
                                instrumentId=instrumentId,
                                exp_date=EXP_DATE,
                                instrumentPrefix=SAMPLE_OPTION_INSTRUMENT_PREFIX,
                                eval_date=startTime,
                                vol=optionData['vol'],
                                rf=RF,
                                position=optionData['position'] if 'position' in optionData else 0) 
            self.currentOptions[instrumentId] = opt
        self.totalTimeUpdating = 0
        self.totalIter = 0
        self.printCurrentState()

    def serializeCurrentState(self):
        stateToSave = {}
        stateToSave['futureVal'] = self.currentFuture.getFutureVal()
        stateToSave['marketData'] = self.marketData[-1]
        stateToSave['featureData'] = self.features[-1]
        stateToSave['time'] = self.lastTimeSaved
        optionDataToSave = {}
        for instrumentId in self.currentOptions:
            optionDataToSave[instrumentId] = {
                'vol': self.currentOptions[instrumentId].vol,
                'position': self.currentOptions[instrumentId].position}
        stateToSave['options'] = optionDataToSave
        stateToSave['positionData'] = self.positionData[-1]
        stateToSave['pnlData'] = self.pnlData[-1]
        return stateToSave

    def printCurrentState(self, isVerbose=False):
        currentState = self.serializeCurrentState()
        timeToPrint = currentState['time'].strftime('%H:%M:%S')
        futureValToPrint = '%.2f' % currentState['futureVal']
        volToPrint = '%.2f' % (currentState['marketData']['Vol'] * 100)
        rvolToPrint = '%.2f' % (currentState['marketData']['R Vol'] * 100)
        mktLowToPrint = '%.2f' % (currentState['marketData'][
                                  'Mkt_Straddle_low'] * 100)
        mktHighToPrint = '%.2f' % (currentState['marketData'][
                                   'Mkt_Straddle_high'] * 100)
        hlavolToPrint = '%.2f' % (currentState['featureData']['HL AVol'] * 100)
        hlrvolToPrint = '%.2f' % (currentState['featureData']['HL RVol'] * 100)
        positionDelta = '%.2f' % currentState['positionData']['delta']
        positionGamma = '%.2f' % currentState['positionData']['gamma']
        positionTheta = '%.2f' % currentState['positionData']['theta']
        pnl = '%.2f' % currentState['pnlData']['Pnl']
        cumulative_pnl = '%.2f' % currentState['pnlData']['Cumulative Pnl']
        # print '\n\n\n\n\n'
        print '%s %s %s %s %s %s %s %s %s %s %s %s %s' % (timeToPrint, futureValToPrint, volToPrint, rvolToPrint, mktLowToPrint, mktHighToPrint, hlavolToPrint, hlrvolToPrint, positionDelta, positionGamma, positionTheta, pnl, cumulative_pnl)
        if not isVerbose:
            return
        print 'Time: ' + str(currentState['time'])
        print 'Future Value: ' + str(currentState['futureVal'])
        print 'Average Time for update: ' + str(0 if self.totalIter == 0 else self.totalTimeUpdating / self.totalIter)
        print '----------Market Data----------'
        print currentState['marketData']
        print '----------Feature Data---------'
        print currentState['featureData']
        print '---------Options---------------'
        print currentState['options']

    def saveCurrentState(self):
        serializedState = self.serializeCurrentState()
        # save last
        np.save(getContinuousSaveStateFilename(), serializedState)
        # save in history
        # TODO: Save other values in csv also
        historyCsvFilename = getHistoryCsvFilename()
        stateDataArray = [serializedState['time'].strftime('%H:%M:%S')]
        stateDataArray.append(serializedState['futureVal'])
        stateDataArray.append(serializedState['marketData']['Vol'] * 100)
        stateDataArray.append(serializedState['marketData']['R Vol'] * 100)
        stateDataArray.append(serializedState['marketData'][
                              'Mkt_Straddle_low'] * 100)
        stateDataArray.append(serializedState['marketData'][
                              'Mkt_Straddle_high'] * 100)
        stateDataArray.append(serializedState['featureData']['HL AVol'] * 100)
        stateDataArray.append(serializedState['featureData']['HL RVol'] * 100)
        stateDataArray.append(serializedState['positionData']['delta'])
        stateDataArray.append(serializedState['positionData']['gamma'])
        stateDataArray.append(serializedState['positionData']['theta'])
        stateDataArray.append(serializedState['pnlData']['Cumulative Pnl'])
        stateDataArray.append(serializedState['pnlData']['Pnl'])
        stateDataArray.append(serializedState['pnlData']['Cash'])
        csvRow = ','.join(map(str, stateDataArray)) + '\n'
        fd = open(historyCsvFilename, 'a')
        fd.write(csvRow)
        fd.close()

    # updates features at regular intervals only
    def updateFeatures(self, timeOfUpdate):
        convertedTime = utils.convert_time(timeOfUpdate)
        if (convertedTime < self.lastTimeSaved + timedelta(0, TIME_INTERVAL_FOR_UPDATES)):
            return
        self.lastTimeSaved = convertedTime
        # tracking perf
        start = time.time()
        # updating vol for each option first
        currentFutureVal = self.currentFuture.getFutureVal()
        for instrumentId in self.currentOptions:
            opt = self.currentOptions[instrumentId]
            if shouldUpdateOption(opt, currentFutureVal):
                opt.get_impl_vol()
        marketDataDf, featureDf = getFeaturesDf(
            timeOfUpdate, self.currentFuture, self.currentOptions, self.marketData[-1], self.features[-1])
        if marketDataDf is not None:
            self.marketData.append(marketDataDf)
        if featureDf is not None:
            self.features.append(featureDf)

        # executing predictor
        threshold = .01
        predictions = executePredictor(timeOfUpdate, self.currentFuture, self.currentOptions, self.marketData[-1], self.features[-1], self.positionData[-1], threshold)
        cash_used = 0
        for prediction in predictions:
            instrumentId = prediction['instrumentId']
            volume = prediction['volume']
            if prediction['type'] != 1:
                volume = -volume
            tradePrice = 0
            optionToOrder = self.currentOptions[instrumentId]
            if optionToOrder:
                tradePrice = optionToOrder.price
            elif instrumentId == self.currentFuture:
                # TODO handle this
                tradePrice = currentFutureVal
            else:
                continue
            fees = tradePrice * 0.001
            cash_used += float(volume)*float(tradePrice)  + float(fees)
            print(instrumentId, tradePrice, volume, cash_used)
            orderToProcess = order.Order(instrumentId=instrumentId, tradePrice=tradePrice, vol=volume, time=timeOfUpdate, fees=fees)
            self.updateWithNewOrder(orderToProcess)

        # Calculating updates position data
        positionsDf, pnlDf = getPosition_PnlDf(self.currentFuture, self.currentOptions, self.pnlData[-1], cash_used)
        if positionsDf is not None:
            self.positionData.append(positionsDf) 
        self.pnlData.append(pnlDf)


        # Savingstate
        self.saveCurrentState()
        end = time.time()
        diffms = (end - start) * 1000
        self.totalTimeUpdating = self.totalTimeUpdating + diffms
        self.totalIter = self.totalIter + 1
        self.printCurrentState()

    def updateWithNewFutureInstrument(self, futureInstrument):
        # self.histFutureInstruments.append(instrument)  # just for storing
        self.currentFuture.updateWithNewInstrument(futureInstrument)
        self.updateFeatures(futureInstrument.time)

    def updateWithNewOptionInstrument(self, optionInstrument):
        # self.addNewOption(optionInstrument)  # just for storing
        changedOption = self.currentOptions[optionInstrument.instrumentId]
        changedOption.updateWithInstrument(
            optionInstrument, self.currentFuture.getFutureVal())
        self.updateFeatures(optionInstrument.time)

    def updateWithNewOrder(self, order):
        if order.isFuture():
            self.currentFuture.updateWithOrder(order)
        else:
            changedOption = self.currentOptions[order.instrumentId]
            changedOption.updateWithOrder(order)
        self.updateFeatures(order.time)

    '''
    ------------------------------------------------------
    ----------- For storing stuff ------------------------
    ------------------------------------------------------
    '''
    def getCurrentFuture(self):
        return self.histFutureInstruments[-1]

    # returns dictionary of instrumentId -> Option class object
    def getAllCurrentOptions(self):
        toRtn = {}
        for instrumentId in self.histOptionInstruments:
            toRtn[instrumentId] = self.histOptionInstruments[instrumentId][-1]
        return toRtn

    # returns Option class object
    def getCurrentOption(self, instrumentId):
        self.ensureInstrumentId(instrumentId)
        # TODO: what happens if array is empty
        return self.histOptionInstruments[instrumentId][-1]

    def ensureInstrumentId(self, instrumentId):
        if instrumentId not in self.histOptionInstruments:
            self.histOptionInstruments[instrumentId] = []

    def addNewOption(self, opt):
        self.ensureInstrumentId(opt.instrumentId)
        self.histOptionInstruments[opt.instrumentId].append(opt)

    '''
    ------------------------------------------------------
    ----------- Process new data -------------------------
    ------------------------------------------------------
    '''
    def processData(self, instrumentsToProcess):
        for instrument in instrumentsToProcess:
            if instrument.isFuture():
                self.updateWithNewFutureInstrument(instrument)
            else:
                self.updateWithNewOptionInstrument(instrument)

    def processOrders(self, ordersToProcess):
        for order in ordersToProcess:
            self.updateWithNewOrder(order)


def getPosition_PnlDf(future, opt_dict, previousPnl, cash_used):
    futureVal =  future.getFutureVal()
    options_arr = []
    for instrumentId in opt_dict:
        if opt_dict[instrumentId].position != 0:
            options_arr.append(opt_dict[instrumentId])

    temp_positiondf = {}
    temp_pnldf = {}
    temp_positiondf['delta'] = 0
    temp_positiondf['gamma'] = 0
    temp_positiondf['theta'] = 0
    temp_positiondf['total_options'] = 0
    temp_pnldf['Cash'] = previousPnl['Cash'] - cash_used
    instrumentsValue = 0

    if future.position != 0:
        temp_positiondf['delta'] += float(future.position) * 1
        instrumentsValue += float(future.position) * float(futureVal)

    for opt in options_arr:
        price, delta, theta, gamma = opt.get_all()
        temp_positiondf['delta'] += float(opt.position) * delta
        temp_positiondf['gamma'] += float(opt.position) * gamma
        temp_positiondf['theta'] += float(opt.position) * theta
        temp_positiondf['total_options'] += float(opt.position)
        instrumentsValue += float(opt.position) * float(price)

    temp_pnldf['Pnl'] = instrumentsValue + temp_pnldf['Cash']
    temp_pnldf['Cumulative Pnl'] = previousPnl['Cumulative Pnl'] + temp_pnldf['Pnl']
    return temp_positiondf, temp_pnldf


def getFeaturesDf(eval_date, future, opt_dict, lastMarketDataDf, lastFeaturesDf):
    fut = future.getFutureVal()
    if fut == 0:
        print('Future not trading')
        return None, None
    else:
        temp_df = {}
        temp_f = {}

        temp_df['Future'] = fut
        delta_arr = []
        vol_arr = []
        var = 0
        try:
            # Loop over all options and get implied vol for each option
            for instrumentId in opt_dict:
                opt = opt_dict[instrumentId]
                if not shouldUpdateOption(opt, fut):
                    continue
                opt.get_price_delta()
                price, delta = opt.calc_price, opt.delta
                if abs(delta) < 0.75:
                    if (delta < 0):
                        delta = 1 + delta
                    delta_arr.append(delta)
                    # TODO: ivol?
                    vol_arr.append(opt.vol)

            # Calculate ATM Vol
            if len(delta_arr) > 0:
                temp_df['Vol'] = atm_vol(delta_arr, vol_arr, 2)
                temp_df['Mkt_Straddle_low'], temp_df[
                    'Mkt_Straddle_high'], delta_low, delta_high = straddle(opt_dict, option.get_index_val(fut, ROLL))
                delta_arr.append(0.5)
                vol_arr.append(temp_df['Vol'])
            else:
                temp_df['Vol'] = lastMarketDataDf['Vol']

            # Calculate Realized Vol
            var = utils.calc_var_RT(
                lastFeaturesDf['Var'], fut, lastMarketDataDf['Future'])
            temp_f['Var'] = var
            temp_df['R Vol'] = np.sqrt(
                252 * var / (1 - utils.calculate_t_days(eval_date, utils.convert_time(eval_date).date() + timedelta(hours=15, minutes=30))))

            # Calculate Features
            hl_iv = 740
            hl_rv = 740 * 3
            temp_f['HL AVol'] = utils.ema_RT(
                lastFeaturesDf['HL AVol'], temp_df['Vol'], hl_iv)
            temp_f['HL RVol'] = utils.ema_RT(
                lastFeaturesDf['HL RVol'], temp_df['R Vol'], hl_rv)
            temp_f['HL Future'] = utils.ema_RT(
                lastFeaturesDf['HL Future'], temp_df['Future'], hl_iv)

            # Combine Features into prediction
            temp_f['Pred'] = temp_f['HL AVol'] + temp_f['HL RVol'] + \
                temp_df['Future'] / temp_f['HL Future'] - 1

            # append data
            return temp_df, temp_f

        except:
            raise
            return lastMarketDataDf, lastFeaturesDf


def followFiles(files):
    for f in files:
        f.seek(0, 2)
    unfinishedLines = [''] * len(files)
    while True:
        readLines = list(map(lambda x: x.readline(), files))
        readOneLine = False
        i = 0
        for readLine in readLines:
            if readLine:
                readOneLine = True
                unfinishedLines[i] = unfinishedLines[i] + readLine
                if unfinishedLines[i].endswith('\n'):
                    yield(i, unfinishedLines[i])
                    unfinishedLines[i] = ''
            i = i + 1

        if not readOneLine:
            time.sleep(0.1)


def follow(logFile):
    logFile.seek(0, 2)
    while True:
        logLine = logFile.readline()
        if not logLine:
            time.sleep(0.1)
            continue
        yield(logLine)


def createHistoryCsvFileIfNeeded():
    historyCsvFilename = getHistoryCsvFilename()
    if os.path.isfile(historyCsvFilename):
        return
    fd = open(historyCsvFilename, 'a')
    headers = ['Time', 'Future', 'Vol', 'R Vol',
               'Straddle_low', 'Straddle_high', 'HL AVol', 'HL RVol', 'position_delta', 'position_gamma', 'position_theta', 'Cumulative Pnl']
    fd.write(','.join(map(str, headers)) + '\n')
    fd.close()


# Follows log files continuously and runs the strategy.
# Saves state continuously. if State has been saved runs from the last saved state
# else runs from constants.py
def startStrategyContinuous():
    createHistoryCsvFileIfNeeded()
    up = None
    if os.path.isfile(getContinuousSaveStateFilename()):
        print 'Reading from saved state'
        stateSaved = np.load(getContinuousSaveStateFilename()).item()
        up = UnderlyingProcessor(stateSaved['futureVal'], stateSaved['options'], stateSaved[
            'marketData'], stateSaved['featureData'], stateSaved['positionData'], stateSaved['pnlData'], stateSaved['time'])
    else:
        print 'Reading from constants'
        up = UnderlyingProcessor(STARTING_FUTURE_VAL, STARTING_OPTIONS_DATA,
                                 START_MARKET_DATA, START_FEATURES_DATA, START_POSITON_DATA, START_PNL_DATA, START_TIME)

    instrumentsDataparser = ds.Dataparser()
    positionsDataparser = ds.OrdersParser()
    logFile = open(OPTIONS_LOG_FILE_PATH, "r")
    ordersFile = open(Orders_LOG_FILE_PATH, "r")
    lines = followFiles([logFile, ordersFile])
    for line in lines:
        (t, lineContent) = line
        if len(lineContent) == 0:
            continue
        if t == 0:
            optionInstrumentsToProcess = instrumentsDataparser.processLines([
                lineContent])
            up.processData(optionInstrumentsToProcess)
        elif t == 1:
            ordersToProcess = positionsDataparser.processLines([lineContent])
            up.processOrders(ordersToProcess)


def startStrategyHistory(historyFilePath):
    createHistoryCsvFileIfNeeded()
    up = UnderlyingProcessor(
        STARTING_FUTURE_VAL, STARTING_OPTIONS_DATA, START_MARKET_DATA, START_FEATURES_DATA, START_POSITON_DATA, START_TIME)
    dataParser = ds.Dataparser()
    with open(historyFilePath) as f:
        for line in f:
            instrumentsToProcess = dataParser.processLines([line])
            up.processData(instrumentsToProcess)

startStrategyContinuous()
# startStrategyHistory('data_0505')
