Install the dependencies using
===================================
pip install -r requirements.txt


Before installing requirements make sure your system has libffi-dev and
libssl-dev libraries installed , required by the https support .

Start scrapping  by executing
===================================
The current version of the code is using python 2.7 .
To scrape the site using the twisted version of the library execute :

**python my_twisted_scrapper.py 'http://www.example.com'**


The twisted version spawns quite large number of connections on the server
resulting in conditions similar to DOS and might lead to pages returning 503
errors. In such scenarios modify the max concurrent connections settings in the
**config.ini** file .

Deprecated threaded version (for reference ) use
python Scrapper.py 'http://www.example.com'


Configurations
==============
Certain configurations for the scrapper can be done via the scrapper *config.ini*
file the various configurations available are as follows

*Starting url*

**START_URL = http://www.example.com/**

*Max concurrent requests done to the server, too high value and server is choked*

**MAX_CONCURRENT_REQUESTS_PER_SERVER = 10**

*Idle ping used for determining the termination of the process*

**IDLE_PING_COUNT = 10**

*comma separated sub domains that need to be skipped*

**DOMAINS_TO_BE_SKIPPED=sub1.example.com,sub2.example.com**



Limitations
============
1.Currently the utility doesn't scrape the pages obtained after loggging in .

2.Handling localhost based urls might require some tweaking .