import urlparse
import logging

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from twisted.internet import reactor
from twisted.internet.defer import Deferred, maybeDeferred, succeed
from twisted.internet.ssl import ClientContextFactory
from twisted.python import log
from twisted.web.client import Agent, getPage, WebClientContextFactory, \
    RedirectAgent
from tldextract import extract


logging.basicConfig(filemode='w', filename='page.log', level=logging.INFO)
logger = logging.getLogger(__name__)

__author__ = 'jayesh'


def extract_base_site(url):
    extracted = extract(url)
    if extracted.domain.endswith("."):
        return extracted.domain[:-1]
    site = "http://{}.{}.{}".format(extracted.subdomain, extracted.domain,
                                    extracted.tld)
    return site


def extract_domain(url):
    extracted = extract(url)
    domain = "{}.{}".format(extracted.domain, extracted.tld)
    if domain.endswith("."):
        return domain[:-1]
    return domain


class WebClientContextFactory(ClientContextFactory):
    def getContext(self, hostname, port):
        return ClientContextFactory.getContext(self)


class MyTwistedPage:
    def __init__(self, url, parent, base_site, base_domain):
        self.url = '' if url is None else url
        self.base_domain = base_domain
        self.response_code = -1
        self.external_url = self.base_domain not in extract_domain(self.url)
        self.errors = []
        self.links = set()
        self.visited = False
        self.parent = parent
        self.base_site = base_site
        self.content_type = "text/html"

    def process_head_response(self, response):
        logger.debug(
            "Called {} for {} ".format('process_head_response', self.url))
        self.response_code = response.code
        self.content_type = "".join(
            response.headers.getRawHeaders('Content-Type', ''))
        if response.code >= 404:
            raise Exception('Failed with error code {}'.format(response.code))

        return response.code


    def process_head_failure(self, failure):
        logger.info("Called {} for {} due to {} ".format('process_head_failure',
                                                         self.url,
                                                         failure.value))
        self.content_type = 'UNKNOWN'
        raise Exception(failure.value)

    def format_link(self, href_value):
        if href_value.startswith('#'):
            link = self.url
        else:
            link = urlparse.urljoin(self.url, href_value, allow_fragments=False)
            link = link if 'javascript:void' not in href_value \
                and not href_value.startswith('mailto') else None
        return link

    def process_get_response(self, response):
        logger.debug(
            "Called {} for {} ".format('process_get_response', self.url))
        if not self.external_url:
            html_source = response
            soup = BeautifulSoup(html_source)
            link_elements = soup.find_all("a")

            link_count = 0
            for link_tag in link_elements:
                link = None
                if link_tag.has_attr('href'):
                    href_value = link_tag['href']
                    link = self.format_link(href_value)
                else:
                    continue

                if link is not None:
                    link_page = MyTwistedPage(link, self, self.base_site,
                                              self.base_domain)
                    self.links.add(link_page)
                    link_page.parent = self
                    link_count += 1

    def process_get_failure(self, response):
        logger.info("Called {} for {} with {} ".format('process_get_failure',
                                                       self.url,
                                                       response.value))
        self.content_type = 'UNKNOWN'

    def make_head_request(self):
        logger.debug("Called {} for {}".format('make_head_request', self.url))
        agent = RedirectAgent(Agent(reactor))
        if 'https' in self.url:
            contextFactory = WebClientContextFactory()
            agent = RedirectAgent(Agent(reactor, contextFactory))

        deferred = agent.request('HEAD', bytes(self.url))

        return deferred

    def make_get_request(self, status):
        logger.debug("Called {} for {}  ".format('make_get_request', self.url))
        d = Deferred()
        if 'text/html' in self.content_type and not self.external_url:
            d = getPage(bytes(self.url), timeout=30)
        else:
            d.callback("No html content")
        return d

    def process(self):
        logger.debug("Called {}".format('process'))
        deferred = self.make_head_request()
        deferred.addCallback(self.process_head_response)
        deferred.addErrback(self.process_head_failure)
        deferred.addCallback(self.make_get_request)
        deferred.addCallback(self.process_get_response)
        deferred.addErrback(self.process_get_failure)
        deferred.addErrback(log.err)
        return deferred

    def obtain_driver(self):
        browser_profile = webdriver.FirefoxProfile()
        browser_profile.add_extension('JSErrorCollector.xpi')
        driver = webdriver.Firefox(firefox_profile=browser_profile)

        return succeed(driver)

    def browse_page(self):
        d = maybeDeferred(self.obtain_driver)
        d.addCallback(self.identify_javascript_errors)
        return d

    def identify_javascript_errors(self, driver):
        driver.get(self.url)
        WebDriverWait(driver, 20).until(lambda d: d.execute_script(
            'return document.readyState') == 'complete')
        try:
            error_messages = driver.execute_script(
                bytes("return window.JSErrorCollector_errors.pump()"))
            self.errors = list(map(lambda x: x['errorMessage'], error_messages))
        except Exception as e:
            logger.error("Encountered error while collecting data from "
                         "jscollector plugin , defaulting to the basic "
                         "mechanism for error collection")
            log_messages = (driver.get_log('browser'))
            for error_entry in log_messages:
                if "Error" in error_entry["message"] and "SEVERE" in \
                        error_entry[
                            'level']:
                    self.errors.append(error_entry)
        driver.quit()

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return self.url.replace("https", 'http') == \
               other.url.replace("https", 'http')

    def __str__(self):
        return "Url: {}," \
               "\tResponse Code : {}" \
               "\tParent : {}" \
               "\tExternal : {}" \
               "\tVisited : {}" \
               "\tErrors : {} " \
            .format(self.url, self.response_code,
                    self.parent.url if self.parent is not None else '',
                    self.external_url, self.visited, self.errors)


if __name__ == "__main__":
    base_url = 'http://www.neevtech.com'
    base_url = 'http://www.slideshare.net/neevtech/nodejs-neev'
    page = MyTwistedPage(base_url, None, base_url, extract_domain(base_url))
    main_deferred = page.make_head_request()
    reactor.run()