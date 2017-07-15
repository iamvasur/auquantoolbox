# **Quick Startup Guide** #

1. Packages to install. Easiest way is via pip  
    * numpy  
    * pandas  
    * pandas-datareader  
    * plotly  

2. Clone/Download this repository.  
```
git clone https://likwidskin@bitbucket.org/likwidskin/trading_scripts.git
```

3.  Navigate to the place where you downloaded the repo. Go inside that folder and run 
```
#!python

python my_trading_params.py
```
This will execute your strategy.

4. Use my_trading_params.py as a template to create your very own strategy. Copy that template to another file 
and then start implementing the methods in that file. Use pair_trading_params.py and meanreversion_trading_params.py as exmaples for motivations.
