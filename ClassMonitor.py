import urllib.request
import urllib.parse
import bs4
import time
from flask import Flask, request, render_template, redirect, url_for
from datetime import datetime
import re
import threading
import json

app = Flask(__name__)

API_KEY = ""
with open("./apiKey.json", "r") as f:
    API_KEY = json.load(f)["key"]

BASE_URL = "https://www2.bellevuecollege.edu/classes/" #Base class access URL
WEBHOOK_URL = "https://maker.ifttt.com/trigger/classes_updated/with/key/" + API_KEY + "?" #IFTTT Webhook trigger

#Helper Functions
def getConfig():
    """ Get the config """
    with open("./config.json", "r") as f:
        return json.load(f)

def setConfig(config):
    """ Set the config """
    with open("./config.json", "w") as f:
        return json.dump(config, f)

config = getConfig() #Load the configuration

currentStatus = {} #Current class status
classTimestamp = "" #When classes were last updated



#Class Functions
            
def checkClasses():
    """ Check the classes and return a dictionary of class types with class ids and number of waitlisted people """
    global classTimestamp
    classes = {};
    classTimestamp = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
    for classType in config["CLASSES"]: #Iterate over each class type (such as "MATH" or "PHYS"
        print("Checking %d class(es) in type %s..." %(len(config["CLASSES"][classType]), classType))
        classes[classType] = {} #Set class name as key to dictionary of IDs
        f = urllib.request.urlopen(BASE_URL + config["QUARTER_NAME"] + "/" + classType) #Open URL
        raw = f.read()
        data = bs4.BeautifulSoup(raw, "html.parser")

        for _id in config["CLASSES"][classType]: #Iterate over each class ID (four digit number)
            print("\tChecking class %s..." %_id)
            res = data.findAll("td", id=re.compile("^availability-" + _id + ".*$")) #Search for appropriate element
            waitlisted = 0
            if len(res) > 0:
                resText = res[0].text
                if "waitlist" in resText: #Full and waitlisted
                    noPeople = int(resText[resText.index(",")+2:resText.index("on")])
                    print("\t\tClass waitlisted with %d people: %s" %(noPeople, _id))
                    waitlisted = -noPeople
                elif "Class full" in resText: #Full but no waitlist described
                    print("\t\tClass full but no waitlist information: %s" %_id)
                    waitlisted = 0
                else: #Not full
                    waitlisted = int(resText[:3])
                    print("\t\tClass not full: %s with %d seats left" %(_id, waitlisted)) 
            else:
                print("\t\tERROR: could not find class")
                config["CLASSES"][classType].remove(_id)
                continue #Skip this loop
            classes[classType][_id] = waitlisted
    return classes

def checkClassChanges():
    """ Get the latest class values and send any notifications, as well as return the new classes """
    try:
        newStatus = checkClasses()
        for className in newStatus:
            for _id in newStatus[className]:
                if (className not in currentStatus or _id not in currentStatus[className] or newStatus[className][_id] != currentStatus[className][_id]): #Notification not sent before 
                    print("Sending notification...")
                    f = urllib.request.urlopen(WEBHOOK_URL + "value1=%s&value2=%s" %(_id, newStatus[className][_id])) #Run the request
                    f.read() #download data
        return newStatus
    except:
        print("Error while checking classes... Trying again")
        return currentStatus #Default back to current status


#Web Server Functions         
@app.route("/")
def onIndex():
    classesHTML = "" #Class add/remove table body
    classesStatusHTML = ""  #Class status table body
    i = 0 #Counter for indexing
    for className in config["CLASSES"]:
        for classId in config["CLASSES"][className]:
            status = currentStatus[className][classId]
            if status == -5: #Full waitlist
                status = "<p class='text-danger'>Waitlist full</p>"
            elif status < 0: #Some waitlist
                status = "<p class='text-warning'>Waitlisted (%d on waitlist)</p>" %(-status)
            elif (status == 0):
                status = "<p class='text-warning'>Class Full</p>"
            elif (status == 1):
                status = "<p class='text-success'>1 seat available</p>"
            else:
                status = "<p class='text-success'>%d seats available</p>" %status
            classesHTML += "<tr>\
                    <td><input class='form-control' type='text' name='CLASSNAME_%d' value='%s' required></td>\
                    <td><input class='form-control' type='text' name='CLASSID_%d' value='%s' required></td>\
                    <td><button class='btn btn-sm btn-danger' onclick='removeRow(event); return false;'>X</button></td>\
                    </tr>" %(i, className, i, classId)
            classesStatusHTML += "<tr>\
                    <td>%s</td>\
                    <td>%s</td>\
                    <td>%s</td>\
                    </tr>" %(className, classId, status)
            i += 1
    return render_template("index.html", quarterName=config["QUARTER_NAME"], timestamp=classTimestamp, classesHTML=classesHTML, classesStatusHTML=classesStatusHTML)

@app.route("/updateConfig", methods=["POST"])
def onUpdateConfig():
    global currentStatus
    config["CLASSES"] = {} #Reset list
    for key in request.form:
        key = key.upper()
        if key in config and key == "QUARTER_NAME":
            config[key] = request.form["quarter_name"]
        elif "CLASSNAME" in key:
            keyId = key[10:] #ID of name/id pair
            if ("CLASSID_" + keyId) in request.form:
                if not request.form["CLASSNAME_" + keyId] in config["CLASSES"]:
                    config["CLASSES"][request.form["CLASSNAME_" + keyId]] = [request.form["CLASSID_" + keyId]]
                else:
                    config["CLASSES"][request.form["CLASSNAME_" + keyId]].append(request.form["CLASSID_" + keyId])
    currentStatus = checkClassChanges()
    setConfig(config)
    return redirect(url_for("onIndex"))

#Main app logic
def serverStart(): #App thread
    app.run(host="0.0.0.0", port="80");

def backgroundStart(): #Background checks thread
    """ Poll the classes as specified in config and get webhook URL on change """
    global currentStatus
    while True:
        currentStatus = checkClassChanges()
        time.sleep(10)

if __name__ == "__main__":
    p1 = threading.Thread(target=serverStart)
    p1.start()
    p2 = threading.Thread(target=backgroundStart)
    p2.start()

    
