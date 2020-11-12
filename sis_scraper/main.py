from dotenv import load_dotenv
import os
import shutil
import requests
from bs4 import BeautifulSoup
import json
import re
import math
from tqdm import tqdm
import urllib.parse
from copy import deepcopy

load_dotenv()


def addConflicts(data):
    for department in data:
        for course in department["courses"]:
            for section in course["sections"]:
                section["conflicts"] = getConflict(
                    data, section["timeslots"], section["subj"] + str(section["crse"])
                )


def getConflict(data, check_timeslots, course_code):
    conflicts = {}

    for department in data:
        for course in department["courses"]:
            for section in course["sections"]:
                for timeslot in section["timeslots"]:
                    for day in timeslot["days"]:
                        # Dont conflict with other sections of the same course (or with self)
                        if course_code == section["subj"] + str(section["crse"]):
                            continue

                        # If this course does not have a timeslot just skip it
                        if timeslot["timeStart"] == -1 or timeslot["timeEnd"] == -1:
                            continue

                        for check_timeslot in check_timeslots:
                            # If this course does not have a timeslot just skip it
                            if (
                                check_timeslot["timeStart"] == -1
                                or check_timeslot["timeEnd"] == -1
                            ):
                                continue

                            # If not happening on the same day skip it
                            if day not in check_timeslot["days"]:
                                continue

                            # If the dates dont overlap skip it
                            if not max(
                                check_timeslot["dateStart"], timeslot["dateStart"]
                            ) < min(check_timeslot["dateEnd"], timeslot["dateEnd"]):
                                continue

                            # There is a conflict
                            if max(
                                check_timeslot["timeStart"], timeslot["timeStart"]
                            ) < min(check_timeslot["timeEnd"], timeslot["timeEnd"]):
                                # JSON does not support hashtables without a value so the value
                                # is always set to true even though just by being in the conflicts
                                # hash table is enough to know it conflicts
                                conflicts[section["crn"]] = True

    return conflicts


# We decided not to use this but I left it just in case
# def reformatJson(data):
#     departments_copy = data
#     reformat = {}
#     for department in departments_copy:
#         reformat[department['code']] = department
#         course_copy = department['courses']
#         reformat[department['code']]['courses'] = {}
#         for course in course_copy:
#             reformat[department['code']]['courses'][f"{course['subj']}-{course['crse']}"] = course
#             sections_copy = course['sections']
#             reformat[department['code']]['courses'][f"{course['subj']}-{course['crse']}"]['sections'] = {}
#             for section in sections_copy:
#                 reformat[department['code']]['courses'][f"{course['subj']}-{course['crse']}"]['sections'][section['crn']] = section
#
#
#     return reformat
#


def getContent(element):
    return " ".join(
        element.encode_contents().decode().strip().replace("&amp;", "&").split()
    )


def getContentFromChild(element, childType):
    if len(element.findAll(childType)) > 0:
        element = element.findAll(childType)[0]
    return getContent(element)


def cleanOutAbbr(text):
    text = re.sub("<abbr.*?>", "", text)
    text = re.sub("<\/abbr>", "", text)
    text = re.sub(
        "\s?\([pP]\)", "", text
    )  # Remove primary instructor indicator (maybe we can use this data somewhere later but for now it is removed)
    text = re.sub("\w+\.\s+", "", text)
    return text


def timeToMilitary(time, useStartTime):
    if "TBA" in time:
        return -1
    if useStartTime:
        time = time.split("-")[0]
    else:
        time = time.split("-")[1]

    offset = 0
    if "pm" in time and "12:" not in time:
        offset = 1200
    return int("".join(time.strip().split(":"))[:4]) + offset


def toTitle(text):
    text = text.title()
    regex = r"\b[iI]+\b"
    matches = re.finditer(regex, text)
    for matchNum, match in enumerate(matches, start=1):
        text = (
            text[: match.start()]
            + text[match.start() : match.end()].upper()
            + text[match.end() :]
        )

    text = text.replace("'S", "'s")

    return text


def calculate_score(columns):
    if not columns:
        return 99999999999  # some arbitrarily large number

    def column_sum(column):
        return sum(map(lambda x: len(x["depts"]) + 3, column))

    mean = sum(map(column_sum, columns)) / len(columns)
    return sum(map(lambda x: abs(mean - column_sum(x)), columns)) / len(columns)


# Recursively finds the most balanced set of columns.
# Since `best` needs to be passed by reference, it's
# actually [best], so we only manipulate best[0].
def optimize_ordering_inner(data, i, columns, best):
    if i == len(data):
        this_score = calculate_score(columns)
        best_score = calculate_score(best[0])

        if this_score < best_score:
            best[0] = deepcopy(columns)
        return

    for column in columns:
        column.append(data[i])
        optimize_ordering_inner(data, i + 1, columns, best)
        column.pop()


def optimize_column_ordering(data, num_columns=3):
    """
    Because we want the QuACS homepage to be as "square-like" as possible,
    we need to re-order departments in such a way that once they're laid out
    in multiple columns, each column is a similar height.
    """

    columns = [[] for _ in range(num_columns)]
    best_result = [[]]

    optimize_ordering_inner(data, 0, columns, best_result)

    best_result = best_result[0]

    for i in range(len(best_result)):
        best_result[i] = sorted(
            best_result[i], key=lambda s: len(s["depts"]), reverse=True
        )

    best_result = sorted(best_result, key=lambda c: len(c[0]["depts"]), reverse=True)

    flattened = []
    for column in best_result:
        flattened.extend(column)

    return flattened


payload = f'sid={os.getenv("RIN")}&PIN={urllib.parse.quote(os.getenv("PASSWORD"))}'
headers = {"Content-Type": "application/x-www-form-urlencoded"}
with requests.Session() as s:  # We purposefully don't use aiohttp here since SIS doesn't like multiple logged in connections
    s.get(url="https://sis.rpi.edu/rss/twbkwbis.P_WWWLogin")
    response = s.request(
        "POST",
        "https://sis.rpi.edu/rss/twbkwbis.P_ValLogin",
        headers=headers,
        data=payload,
    )

    if b"Welcome" not in response.text.encode("utf8"):
        print("Failed to log into sis")
        exit(1)

    for term in tqdm(os.listdir("data")):
        url = "https://sis.rpi.edu/rss/bwskfcls.P_GetCrse_Advanced"
        payload = f"rsts=dummy&crn=dummy&term_in={term}&sel_subj=dummy&sel_day=dummy&sel_schd=dummy&sel_insm=dummy&sel_camp=dummy&sel_levl=dummy&sel_sess=dummy&sel_instr=dummy&sel_ptrm=dummy&sel_attr=dummy&"

        with open(f"data/{term}/schools.json") as f:
            for school in json.load(f):
                for dept in school["depts"]:
                    payload += f"sel_subj={dept['code']}&"

        payload += "sel_crse=&sel_title=&sel_from_cred=&sel_to_cred=&sel_camp=%25&sel_ptrm=%25&"
        if int(term) <= 201101:  # SIS removed a field after this semester
            payload += "sel_instr=%25&"
        payload += "begin_hh=0&begin_mi=0&begin_ap=a&end_hh=0&end_mi=0&end_ap=a&SUB_BTN=Section+Search&path=1"

        # This payload is for testing. It will only return CSCI classes and will therefore be a bit faster
        # payload = f'rsts=dummy&crn=dummy&term_in={os.getenv("CURRENT_TERM")}&sel_subj=dummy&sel_day=dummy&sel_schd=dummy&sel_insm=dummy&sel_camp=dummy&sel_levl=dummy&sel_sess=dummy&sel_instr=dummy&sel_ptrm=dummy&sel_attr=dummy&sel_subj=CSCI&sel_subj=LGHT&sel_crse=&sel_title=&sel_from_cred=&sel_to_cred=&sel_camp=%25&sel_ptrm=%25&begin_hh=0&begin_mi=0&begin_ap=a&end_hh=0&end_mi=0&end_ap=a&SUB_BTN=Section+Search&path=1'

        headers = {}
        response = s.request("POST", url, headers=headers, data=payload)

        if "No classes were found that meet your search criteria" in response.text:
            print(f"Term {term} has no classes!")
            print(payload)
            shutil.rmtree(
                f"data/{term}"
            )  # This term doesn't have classes, just remove it and continue
            continue

        data = []

        # print(response.text.encode('utf8'))
        soup = BeautifulSoup(response.text.encode("utf8"), "html.parser")
        table = soup.findAll("table", {"class": "datadisplaytable"})[0]
        rows = table.findAll("tr")
        current_department = None
        current_code = None
        current_courses = None

        last_subject = None
        last_course_code = None
        for row in rows:
            th = row.findAll("th")
            if len(th) != 0:
                if "ddtitle" in th[0].attrs["class"]:
                    # if(current_department):
                    data.append(
                        {"name": toTitle(getContent(th[0])), "code": "", "courses": []}
                    )
            else:
                td = row.findAll("td")
                if "TBA" not in getContent(td[8]):
                    timeslot_data = {
                        "days": list(getContent(td[8])),
                        "timeStart": timeToMilitary(
                            getContentFromChild(td[9], "abbr"), True
                        ),
                        "timeEnd": timeToMilitary(
                            getContentFromChild(td[9], "abbr"), False
                        ),
                        "instructor": ", ".join(
                            [
                                x.strip()
                                for x in cleanOutAbbr(getContent(td[19])).split(",")
                            ]
                        ),
                        "dateStart": getContentFromChild(td[20], "abbr").split("-")[0],
                        "dateEnd": getContentFromChild(td[20], "abbr").split("-")[1],
                        "location": getContentFromChild(td[21], "abbr"),
                    }
                else:
                    timeslot_data = {
                        "dateEnd": "",
                        "dateStart": "",
                        "days": [],
                        "instructor": "",
                        "location": "",
                        "timeEnd": -1,
                        "timeStart": -1,
                    }

                if len(getContent(td[1])) == 0:
                    data[-1]["courses"][-1]["sections"][-1]["timeslots"].append(
                        timeslot_data
                    )
                    continue

                credit_min = float(getContent(td[6]).split("-")[0])
                credit_max = credit_min
                if len(getContent(td[6]).split("-")) > 1:
                    credit_max = float(getContent(td[6]).split("-")[1])

                section_data = {
                    # "select":getContentFromChild(td[0], 'abbr'),
                    "crn": int(getContentFromChild(td[1], "a")),
                    "subj": getContent(td[2]),
                    "crse": int(getContent(td[3])),
                    "sec": getContent(td[4]),
                    # "cmp":getContent(td[5]),
                    "credMin": credit_min,
                    "credMax": credit_max,
                    "title": toTitle(getContent(td[7])),
                    "cap": int(getContent(td[10])),
                    "act": int(getContent(td[11])),
                    "rem": int(getContent(td[12])),
                    # "wlCap":int(getContent(td[13])),
                    # "wlAct":int(getContent(td[14])),
                    # "wlRem":int(getContent(td[15])),
                    # "xlCap":getContent(td[16]),
                    # "xlAct":getContent(td[17]),
                    # "xlRem":getContent(td[18]),
                    "attribute": getContent(td[22]) if 22 < len(td) else "",
                    "timeslots": [timeslot_data],
                }

                if (
                    section_data["subj"] == last_subject
                    and section_data["crse"] == last_course_code
                ):
                    data[-1]["courses"][-1]["sections"].append(section_data)
                    continue

                last_subject = getContent(td[2])
                last_course_code = int(getContent(td[3]))
                data[-1]["courses"].append(
                    {
                        "title": toTitle(getContent(td[7])),
                        "subj": getContent(td[2]),
                        "crse": int(getContent(td[3])),
                        "id": getContent(td[2]) + "-" + getContent(td[3]),
                        "sections": [section_data],
                    }
                )

                if len(getContent(td[2])) > 0:
                    data[-1]["code"] = getContent(td[2])

        # This is for the old conflict method that has a list for each class that it conflicts with
        # addConflicts(data)

        # data = reformatJson(data)

        # print(json.dumps(data,sort_keys=False,indent=2))
        with open(f"data/{term}/courses.json", "w") as outfile:
            json.dump(data, outfile, sort_keys=False, indent=2)

        # Remove schools which have no courses, then format it for the homepage
        with open(f"data/{term}/schools.json", "r") as all_schools_f:
            all_schools = json.load(all_schools_f)

        schools = []
        for possible_school in all_schools:
            res_school = {"name": possible_school["name"], "depts": []}
            for target_dept in possible_school["depts"]:
                matching_depts = list(
                    filter(lambda d: d["code"] == target_dept["code"], data)
                )
                if matching_depts:
                    res_school["depts"].append(target_dept)
            if res_school["depts"]:
                schools.append(res_school)

        school_columns = optimize_column_ordering(schools)
        with open(f"data/{term}/schools.json", "w") as schools_f:
            json.dump(school_columns, schools_f, sort_keys=False, indent=2)

        # Generate binary conflict output
        TIME_START = 0
        TIME_END = 2400
        NUM_HOURS = int((TIME_END - TIME_START) / 100)

        MINUTE_GRANULARITY = 10
        NUM_MIN_PER_HOUR = 60 // MINUTE_GRANULARITY

        offset = lambda x: x * NUM_HOURS * NUM_MIN_PER_HOUR

        day_offsets = {
            "M": offset(0),
            "T": offset(1),
            "W": offset(2),
            "R": offset(3),
            "F": offset(4),
            "S": offset(5),
            "U": offset(6),
        }

        BIT_VEC_SIZE = offset(len(day_offsets))

        conflicts = {}
        crn_to_courses = {}
        for dept in data:
            for course in dept["courses"]:
                for section in course["sections"]:
                    crn_to_courses[section["crn"]] = course["id"]

                    conflict = [0] * BIT_VEC_SIZE
                    for time in section["timeslots"]:
                        for day in time["days"]:
                            for hour in range(TIME_START, TIME_END, 100):
                                for minute in range(0, 60, MINUTE_GRANULARITY):
                                    if (
                                        time["timeStart"] <= hour + minute
                                        and time["timeEnd"] > hour + minute
                                    ):
                                        minute_idx = minute // 10
                                        hour_idx = hour // 100
                                        conflict[
                                            day_offsets[day]
                                            + hour_idx * (60 // MINUTE_GRANULARITY)
                                            + minute_idx
                                        ] = 1

                    conflicts[section["crn"]] = "".join(str(e) for e in conflict)
        # If 0 courses, or exactly one course, occupies a slot in the conflict bitstring, we can safely remove it to save space
        # as that implies no conflicts are possible in that block.
        # The following code computes a list of candidates that fit this criteria
        unnecessary_indices = [bit_index for bit_index in range(0, BIT_VEC_SIZE)
                if sum(int(conflicts[section_crn][bit_index]) for section_crn in conflicts) <= 1]
        # Reverse the list as to not break earlier offsets
        conflicts_to_prune = reversed(unnecessary_indices)

        # Prune the bits in `conflicts_to_prune` from all the bitstrings
        for section_crn in conflicts:
            bitstr = conflicts[section_crn]
            for x in conflicts_to_prune:
                conflicts[section_crn] = bitstr[:x] + bitstr[x+1:]
        # Compute the proper bit vec length for quacs-rs
        BIT_VEC_SIZE = math.ceil((BIT_VEC_SIZE - len(unnecessary_indices)) / 64)
        with open(f"data/{term}/mod.rs", "w") as f:  # -{os.getenv("CURRENT_TERM")}
            f.write(
                """\
//This file was automatically generated. Please do not modify it directly
use ::phf::{{phf_map, Map}};

pub const BIT_VEC_LEN: usize = """
                + str(BIT_VEC_SIZE)
                + """;

pub static CRN_TIMES: Map<u32, [u64; BIT_VEC_LEN]> = phf_map! {
"""
            )

            for crn, conflict in conflicts.items():
                rust_array = f"\t{crn}u32 => ["
                for i in range(0, BIT_VEC_SIZE * 64, 64):
                    if i != 0:
                        rust_array += ", "
                    rust_array += str(int(conflict[i : i + 64], 2))
                rust_array += "],\n"

                f.write(rust_array)

            f.write(
                """
};

pub static CRN_COURSES: Map<u32, &'static str> = phf_map! {
"""
            )

            for crn, course in crn_to_courses.items():
                f.write(f'\t{crn}u32 => "{course}",\n')
            f.write("};")
