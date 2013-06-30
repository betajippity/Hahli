import xml.etree.ElementTree as ET
import os
import sqlite3
import urllib
import time
import json
from HTMLParser import HTMLParser
from datetime import datetime
import hashlib
import imghdr

#Takes in a subs database and three strings for feed XML address, feed URL, and feed title, and adds a new feed entry to the given subs database.
def addFeedToSubsDb(subsDb, feedXML, feedURL, feedTitle):
	db = subsDb.cursor()
	if feedXML[-1]=='_':
		feedXML = feedXML[:-1]
	feedQuery = (feedXML, feedTitle, feedURL)
	#check if feed already exists in db and insert if it does not
	selectedRow = db.execute('SELECT * FROM feeds WHERE feedURL=?', (feedXML,)).fetchone()
	if selectedRow == None:
		db.execute('INSERT INTO feeds VALUES (?,?,?)', feedQuery)
		subsDb.commit()
		print "Added feed "+feedXML+" to database."
	else:
		print "Error: Feed "+feedXML+" already exists in database."

#Takes in a path to an opml file and adds contents to a subs database in the given rssToolDir directory.
def createSubsDbFromOPML(opmlFile, rssToolDir):
	#load opml
	parseTree = ET.parse(opmlFile).getroot()
	#setup sqlite db for subscriptions
	subsDb = openSubsDb(rssToolDir)
	#loop through subscriptions and add each subscription to subsDb
	for feed in parseTree[1]:
		addFeedToSubsDb(subsDb, feed.attrib['xmlUrl'], feed.attrib['htmlUrl'], feed.attrib['title'])

#Opens or creates a subs database in the current rssToolDir directory.
def openSubsDb(rssToolDir):
	#setup sqlite db for subscriptions
	subsDb = sqlite3.connect(rssToolDir+'subscriptions.db')
	dbc = subsDb.cursor()
	#check if feeds table exists and create if necessary
	dbc.execute('''CREATE TABLE IF NOT EXISTS feeds ("feedURL" TEXT PRIMARY KEY  NOT NULL , "name" TEXT, "htmlURL" TEXT)''')
	subsDb.commit()
	return subsDb

#Takes in feed XML address and downloads corresponding Google Reader feed archive
def downloadFeedArchiveFromGReader(feedXML, rssToolDir):
	#setup feeds dir
	if os.path.exists(rssToolDir+'feeds') == False:
		os.makedirs(rssToolDir+'feeds')
	#process URLs and filenames, make subdir for feed if necessary
	xmlfilename = feedXML.replace('http://','').replace('/','_')
	if xmlfilename[-1]=='_':
		xmlfilename = xmlfilename[:-1]
	if os.path.exists(rssToolDir+'feeds/'+xmlfilename) == False:
		os.makedirs(rssToolDir+'feeds/'+xmlfilename)
	#start by stripping any trailing /s from the feedURL, pull the archive, and then repeat with a trailing / added back.
	if feedXML[-1]=='/':
		feedXML = feedXML[:-1]
	greaderurl = "http://www.google.com/reader/api/0/stream/contents/feed/"+urllib.quote(feedXML, '')+"?n=9999&ot=0"
	#download archive for feedURL with no trailing /
	archivenumber = ""
	urlc = urllib.urlopen(greaderurl)
	if urlc.getcode()!=404:
		archive = ""
		try:
			archive = urlc.read()
			print "Downloading archive of " + feedXML + " from Google Reader API"
		except IOError:
			print "Delaying for server to catch up..."
			time.sleep(5)
			try:
				archive = urlc.read()
				print "Downloading archive of " + feedXML + " from Google Reader API"
			except IOError:
				print "Feed " + feedXML + " archive could not be downloaded from Google Reader API"
		file = open(rssToolDir+"feeds/"+xmlfilename+"/archive"+archivenumber+".json", 'w')
		file.write(archive)
		file.close()
		archivenumber = "2"
	#add / back in and download archive
	feedXML = feedXML+"/"
	greaderurl = "http://www.google.com/reader/api/0/stream/contents/feed/"+urllib.quote(feedXML, '')+"?n=9999&ot=0"
	#download archive for feedURL with trailing /
	urlc = urllib.urlopen(greaderurl)
	if urlc.getcode()!=404:
		archive = ""
		try:
			archive = urlc.read()
			print "Downloading archive of " + feedXML + " from Google Reader API"
		except IOError:
			print "Delaying for server to catch up..."
			time.sleep(5)
			try:
				archive = urlc.read()
				print "Downloading archive of " + feedXML + " from Google Reader API"
			except IOError:
				print "Feed " + feedXML + " archive could not be downloaded from Google Reader API"
		file = open(rssToolDir+"feeds/"+xmlfilename+"/archive"+archivenumber+".json", 'w')
		file.write(archive)
		file.close()

#Takes in a subs database and downloads feed archives from Google Reader API for all feeds in the database
def getAllArchives(subsDb, rssToolDir):
	db = subsDb.cursor()
	feeds = db.execute('SELECT * FROM feeds').fetchall()
	#setup feeds dir
	if os.path.exists(rssToolDir+'feeds') == False:
		os.makedirs(rssToolDir+'feeds')
	#loop over feeds and download each feed's Google Reader archive
	for feed in feeds:
		downloadFeedArchiveFromGReader(feed[0], rssToolDir)

#Class extending HTML parser to pull out images
class imgParse(HTMLParser):
    imgLinks = []
    def handle_starttag(self, tag, attrs):
        if tag=="img":
            self.imgLinks.append(dict(attrs)["src"])
    def clear(self):
    	self.imgLinks = []

#Opens or creates a feed database in the current rssToolDir directory
def openFeedDb(feedXML, rssToolDir):
	#create subdir for feed if necessary
	xmlfilename = feedXML.replace('http://','').replace('/','_')
	if xmlfilename[-1]=='_':
		xmlfilename = xmlfilename[:-1]
	if os.path.exists(rssToolDir+'feeds/'+xmlfilename) == False:
		os.makedirs(rssToolDir+'feeds/'+xmlfilename)
	#setup sqlite db for subscriptions
	feedDb = sqlite3.connect(rssToolDir+'feeds/'+xmlfilename+'/feed.db')
	dbc = feedDb.cursor()
	#check if feeds table exists and create if necessary
	dbc.execute('''CREATE TABLE IF NOT EXISTS posts ("id" VARCHAR PRIMARY KEY  NOT NULL , "title" TEXT, "url" TEXT, "published" DATETIME, "updated" DATETIME, "content" TEXT)''')
	feedDb.commit()
	return feedDb

#Adds all entries in a Google Reader archive to a feed database. Optionally will download images too if cacheImages is true
def addArchiveToFeedDb(feedXML, rssToolDir):
	#get our feed database
	feedDb = openFeedDb(feedXML, rssToolDir)
	#get our archive json
	xmlfilename = feedXML.replace('http://','').replace('/','_')
	if xmlfilename[-1]=='_':
		xmlfilename = xmlfilename[:-1]
	jd = open(rssToolDir+"feeds/"+xmlfilename+"/archive.json").read()
	archiveData = json.loads(jd)
	for entry in reversed(archiveData["items"]):
		addArchiveEntryToFeedDb(feedXML, feedDb, entry, True, rssToolDir)
	if os.path.isfile(rssToolDir+"feeds/"+xmlfilename+"/archive2.json") == True:
		jd = open(rssToolDir+"feeds/"+xmlfilename+"/archive2.json").read()
		archiveData = json.loads(jd)
		for entry in reversed(archiveData["items"]):
			addArchiveEntryToFeedDb(feedXML, feedDb, entry, True, rssToolDir)
	feedDb.close()

#Adds a Google Reader archive entry as a post to a feed database. Optionally will download images too if cacheImages is true
def addArchiveEntryToFeedDb(feedXML, feedDb, archiveEntry, cacheImages, rssToolDir):
	dbc = feedDb.cursor()
	post = ""
	if archiveEntry.has_key("content"):
		post=archiveEntry["content"]["content"]
	elif archiveEntry.has_key("summary"):
		post=archiveEntry["summary"]["content"]
	else:
		print "Error: no content in feed"
		return
	post = urllib.unquote(post)
	#get ID for post by hashing title with date added to front
	hashstring = str(archiveEntry["title"].encode('ascii', 'ignore'))+str(post.encode('ascii', 'ignore'))
	id = hashlib.sha224(hashstring).hexdigest()
	if cacheImages==True:
		#setup images dir
		xmlfilename = feedXML.replace('http://','').replace('/','_')
		if xmlfilename[-1]=='_':
			xmlfilename = xmlfilename[:-1]
		imagedir = rssToolDir+"feeds/"+xmlfilename;
		if os.path.exists(imagedir+'/images') == False:
			os.makedirs(imagedir+'/images')
		#get image URLs
		h=imgParse()
		h.clear()
		h.feed(post)
		imageLinks = h.imgLinks
		#download images, rename, and replace image URLs in posts
		j = 0
		for image in imageLinks:
			imagequoted = image
			image = urllib.unquote(image)
			targetfile = image.rpartition('/')[2]
			targetfile = str(j)
			try:
				downloadImage(image, imagedir+"/images/"+str(id)+'_'+targetfile)
			except IOError:
				print "Delaying for server to catch up..."
				time.sleep(5)
				try:
					downloadImage(image, imagedir+"/images/"+str(id)+'_'+targetfile)
				except IOError:
					print "Image download failed, skipping..."
			post = post.replace('src="'+str(imagequoted), urllib.unquote('src="/images/'+str(id)+'_'+targetfile))
			post = post.replace("src="+str(imagequoted), urllib.unquote("src='/images/"+str(id)+'_'+targetfile))
			j = j+1
	#package post data into a row for db
	publishedTime = datetime.fromtimestamp(archiveEntry["published"])
	updatedTime = datetime.fromtimestamp(archiveEntry["updated"])
	title = archiveEntry["title"]
	url = ""
	if archiveEntry.has_key("alternate"):
		url = archiveEntry["alternate"][0]["href"]
	postQuery = (id, title, url, publishedTime, updatedTime, post)
	#check if post already exists in db and insert if it does not
	selectedRow = dbc.execute('SELECT * FROM posts WHERE id=?', (id,)).fetchone()
	if selectedRow == None:
		dbc.execute('INSERT INTO posts VALUES (?,?,?,?,?,?)', postQuery)
		feedDb.commit()
		print "Added post with ID "+str(id)+" to db."
	else:
		i = 0
		print "Warning: Post with ID "+str(id)+" already exists in db."

#Downloads a given image to the given file
def downloadImage(imageURL, targetFile):
	imageData = urllib.urlopen(imageURL).read()
	imageType = imghdr.what(None, imageData)
	imageFile = open(targetFile+"."+imageType, 'w')
	imageFile.write(imageData)
	imageFile.close()

opmlFile = "/Users/karlli/Desktop/data/subscriptions.xml"
rootDir = "/Users/karlli/Desktop/data/"

#createSubsDbFromOPML(opmlFile, rssToolDir)
#getAllArchives(openSubsDb(rssToolDir), rssToolDir)

#subsDb = openSubsDb(rssToolDir)
#addFeedToSubsDb(subsDb, "http://www.theverge.com/rss/index.xml", "http://www.theverge.com/", "The Verge")
#downloadFeedArchiveFromGReader("http://www.theverge.com/rss/index.xml", rssToolDir)
#openFeedDb("http://www.theverge.com/rss/index.xml", rssToolDir)
#addArchiveToFeedDb("http://bertrand-benoit.com/blog/feed", rootDir)