
def activeHomeworkID():
    configfile = open("config.txt", "r")
    configlines = configfile.readlines()
    configfile.close()

    #Convert config lines to a dictionary
    for line in configlines:
        if ":" in line:
            key, value = line.split(":", 1)
            if key.strip() == "HOMEWORK":
                return value.strip()
    return None