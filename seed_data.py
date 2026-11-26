"""Rebuilds the demo data in data/.

Run `python seed_data.py` any time you want to reset the app to a clean,
realistic starting point. It writes:
  data/complaints.db           the SQLite database the app uses by default
  data/sample_complaints.json  the same records as a JSON data file
  data/sample_complaints.csv   the same records in CSV form (importable)
  data/legacy_import_demo.csv  a messy file for trying the bulk importer
"""
import csv
import glob
import os

import storage
from manager import ComplaintManager

# name, roll no, category, priority, status, filed, closed, description, note
RECORDS = [
    ("Aarav Mehta", "22CS1042", "Hostel", "High", "Resolved", "2026-08-12", "2026-08-15",
     "Water heater in Block B room 214 has not worked for a week.", "Heater element replaced by maintenance."),
    ("Priya Nair", "22EC1015", "Library", "Low", "Resolved", "2026-08-14", "2026-08-30",
     "Reference books for Signals and Systems are missing from the shelf.", "Two copies ordered and shelved."),
    ("Rohan Verma", "21ME1120", "Canteen", "Medium", "Resolved", "2026-08-18", "2026-08-24",
     "Food quality dropped sharply in the evening mess, found hair in the rice.", "Vendor warned in writing and kitchen inspected."),
    ("Sneha Reddy", "23CS1007", "Academics", "High", "In Progress", "2026-09-02", "",
     "Internal marks for the Data Structures lab were never uploaded on the portal.", ""),
    ("Karthik Iyer", "22IT1033", "Transport", "Medium", "Resolved", "2026-09-03", "2026-09-12",
     "College bus route 7 arrives about 30 minutes late almost every day.", "Departure time shifted by 20 minutes."),
    ("Ananya Das", "21CE1050", "Infrastructure", "Critical", "Resolved", "2026-09-05", "2026-09-06",
     "Ceiling fan in lecture hall C-12 is hanging loose and could fall.", "Fan removed and refixed by the electrician."),
    ("Vikram Singh", "22CS1088", "Administration", "Medium", "Rejected", "2026-09-07", "2026-09-15",
     "Request to waive the late fee because the bank server was down.", "Bank confirmed there was no outage on the payment date."),
    ("Meera Joshi", "23EC1021", "Hostel", "High", "Open", "2026-09-10", "",
     "Wifi in girls hostel block A drops every night after 10 pm.", ""),
    ("Arjun Patel", "22ME1064", "Library", "Low", "Resolved", "2026-09-11", "2026-09-20",
     "Library closes at 6 pm, we need extended hours before exams.", "Hours extended to 9 pm during exam weeks."),
    ("Divya Menon", "21IT1012", "Canteen", "Low", "Open", "2026-09-14", "",
     "Please add more vegetarian options to the lunch menu.", ""),
    ("Siddharth Rao", "22CS1101", "Infrastructure", "High", "In Progress", "2026-09-16", "",
     "Projector in room 304 flickers and goes blank during lectures.", ""),
    ("Isha Kapoor", "23CE1018", "Academics", "Medium", "Resolved", "2026-09-18", "2026-09-29",
     "Timetable clash between Fluid Mechanics and the elective on Thursdays.", "Elective slot moved to Friday."),
    ("Nikhil Gupta", "21CS1076", "Hostel", "Critical", "Resolved", "2026-09-20", "2026-09-21",
     "Exposed wiring near the switchboard in room 105, sparks were seen.", "Wiring replaced, electrician report attached."),
    ("Pooja Sharma", "22EC1040", "Transport", "Low", "Open", "2026-09-22", "",
     "Bus pass card reader at the main gate is not scanning.", ""),
    ("Rahul Nambiar", "23ME1009", "Administration", "High", "Resolved", "2026-09-25", "2026-10-04",
     "Scholarship certificate is still pending after three visits to the office.", "Certificate issued and handed over."),
    ("Kavya Pillai", "22IT1055", "Infrastructure", "Medium", "Resolved", "2026-09-27", "2026-10-08",
     "Water cooler on the second floor of the main building is out of order.", "Cooler repaired and filter changed."),
    ("Aditya Bhat", "21CS1093", "Library", "Medium", "Open", "2026-10-01", "",
     "Digital library login keeps rejecting valid student credentials.", ""),
    ("Shreya Banerjee", "23CS1030", "Hostel", "Medium", "In Progress", "2026-10-03", "",
     "Mess timings clash with evening labs, requesting a later dinner slot.", ""),
    ("Manoj Kumar", "22CE1002", "Canteen", "High", "Resolved", "2026-10-05", "2026-10-09",
     "Several students fell sick after eating at the canteen on Monday.", "Food samples tested and supplier changed."),
    ("Lakshmi Prasad", "21EC1066", "Academics", "Low", "Open", "2026-10-07", "",
     "Syllabus copy for the Microwave Engineering elective is outdated.", ""),
    ("Harsh Vardhan", "23IT1044", "Transport", "High", "Open", "2026-10-09", "",
     "No bus service is available for the late evening lab batch after 7 pm.", ""),
    ("Tanvi Choudhary", "22ME1077", "Infrastructure", "Low", "Resolved", "2026-10-10", "2026-10-30",
     "Bicycle stand near the workshop has no roof and no lighting.", "Shed approved and built."),
    ("Yash Malhotra", "21CS1015", "Administration", "Medium", "In Progress", "2026-10-12", "",
     "Hall ticket shows a wrong date of birth, needs correction before exams.", ""),
    ("Aishwarya Rao", "22CS1120", "Hostel", "Low", "Resolved", "2026-10-13", "2026-10-27",
     "Laundry machines in block C have been broken for two weeks.", "Two machines repaired."),
    ("Devansh Jain", "23EC1002", "Library", "Low", "Resolved", "2026-10-14", "2026-10-19",
     "Photocopier on the library ground floor keeps jamming.", "Serviced by the vendor."),
    ("Neha Agarwal", "22IT1009", "Academics", "High", "Open", "2026-10-16", "",
     "Re-evaluation result for Operating Systems is delayed beyond the notified date.", ""),
    ("Sanjay Krishnan", "21ME1031", "Infrastructure", "Critical", "In Progress", "2026-10-18", "",
     "Drain behind the workshop overflows and floods the walkway when it rains.", ""),
    ("Ritika Saxena", "23CE1045", "Canteen", "Medium", "Open", "2026-10-20", "",
     "Prices at the canteen were raised without any notice to students.", ""),
    ("Abhishek Thakur", "22CS1056", "Hostel", "High", "Resolved", "2026-10-22", "2026-10-26",
     "Room 308 has a leaking roof and my books and laptop bag got wet.", "Roof patched and room cleaned."),
    ("Swathi Naidu", "21IT1088", "Transport", "Medium", "Rejected", "2026-10-24", "2026-11-02",
     "Request for a dedicated bus to the railway station every weekend.", "Not feasible, the existing city bus covers the route."),
    ("Gaurav Mishra", "23ME1020", "Administration", "Low", "Resolved", "2026-10-26", "2026-11-05",
     "Bonafide certificate takes more than a week to be issued.", "Turnaround reduced to two days."),
    ("Ayesha Khan", "22EC1090", "Academics", "Medium", "In Progress", "2026-10-28", "",
     "Lab manual for VLSI is not available and the lab hours are too short.", ""),
    ("Varun Tripathi", "21CS1047", "Library", "High", "Open", "2026-10-30", "",
     "Printer in the computer lab library section is not connected to the network.", ""),
    ("Sonal Gupta", "23IT1016", "Hostel", "Medium", "Open", "2026-11-02", "",
     "Mosquito problem near the hostel garden, fogging has not been done.", ""),
    ("Dhruv Anand", "22CE1033", "Infrastructure", "High", "Open", "2026-11-04", "",
     "Broken staircase railing near the east block exit.", ""),
    ("Pranav Kulkarni", "21EC1005", "Canteen", "Low", "Resolved", "2026-11-06", "2026-11-11",
     "Tea is served cold during the morning break.", "Kitchen staff instructed, issue closed."),
    ("Bhavna Yadav", "22CS1111", "Academics", "Critical", "Open", "2026-11-08", "",
     "Exam seating list is missing my name two days before the semester exam.", ""),
    ("Imran Sheikh", "23CS1099", "Administration", "Medium", "Open", "2026-11-10", "",
     "Fee receipt for the third semester is not reflected in the student account.", ""),
    ("Tara Fernandes", "21ME1059", "Other", "Low", "Open", "2026-11-12", "",
     "Lost and found counter has no fixed timings.", ""),
    ("Omkar Patil", "22IT1070", "Hostel", "Medium", "Open", "2026-11-18", "",
     "Study room lights are too dim and two tube lights are dead.", ""),
    # boundary case: description is exactly the 10 character minimum
    ("Zoya Ali", "22EC1999", "Other", "Low", "Open", "2026-11-19", "",
     "Fan noisy.", ""),
    # repeat filer, to show the REPEAT warning
    ("Aarav Mehta", "22CS1042", "Infrastructure", "Medium", "Open", "2026-11-15", "",
     "Charging sockets in classroom 2B are dead on the left side.", ""),
    ("Aarav Mehta", "22CS1042", "Library", "Low", "Open", "2026-11-17", "",
     "Silent zone on the first floor is always noisy and unmonitored.", ""),
]

CSV_COLUMNS = ["student_name", "roll_no", "category", "description", "priority",
               "date_filed", "status", "date_resolved", "resolution_note"]

# A deliberately messy legacy file: 3 good rows, 9 that should be rejected.
LEGACY_ROWS = [
    ["Mohit Arora", "22CS1201", "Library", "Seat reservation system for the reading hall is not working.", "Medium", "2026-11-01", "Open", "", ""],
    ["Julie D", "CS-77", "Hostel", "Hot water supply stops at 7 am daily in block D.", "High", "2026-11-02", "Open", "", ""],
    ["Raj Pandey", "22ME1301", "Gym", "Gym equipment is rusted and unsafe to use.", "Medium", "2026-11-03", "Open", "", ""],
    ["Neel Shah", "23CE1105", "Canteen", "Hot", "Low", "2026-11-04", "Open", "", ""],
    ["Fatima Zaid", "21IT1200", "Transport", "Bus stop shelter near gate 2 has collapsed.", "High", "2026-13-05", "Open", "", ""],
    ["Kunal Sethi", "22EC1303", "Academics", "Request extra classes for Digital Signal Processing.", "Low", "2027-01-10", "Open", "", ""],
    ["Leela Menon", "23CS1210", "Infrastructure", "Lift in the admin block stops between floors.", "Critical", "2026-11-05", "Resolved", "2026-11-07", "Lift serviced and certified."],
    ["Omar Faruk", "21CE1220", "Hostel", "Rooms are not cleaned on weekends.", "Urgent", "2026-11-06", "Open", "", ""],
    ["Pia Roy", "22IT1230", "Library", "Old magazines should be removed from the reading hall.", "Low", "2026-11-07", "Resolved", "", ""],
    ["Aarav Mehta", "22CS1042", "Hostel", "Water heater in Block B room 214 has not worked for a week.", "High", "2026-11-08", "Open", "", ""],
    ["Tina Thomas", "23ME1240", "Transport", "Bus route 3 skips the stop near the market.", "Medium", "2026-11-09", "Open", "", ""],
    ["R2D2!!", "22CS1250", "Other", "Droids are not allowed in the lab and this is unfair.", "Low", "2026-11-10", "Open", "", ""],
]


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows)


def build_store(path):
    """Create a fresh data file at `path` (.db or .json) holding the sample records."""
    for leftover in glob.glob(path + "*"):
        os.remove(leftover)
    manager = ComplaintManager(path)
    for name, roll, category, priority, status, filed, closed, description, note in RECORDS:
        manager.add(name, roll, category, description, priority, filed,
                    status=status, date_resolved=closed, note=note, commit=False)
    manager.flush()
    return len(manager.complaints)


def main():
    os.makedirs(storage.DATA_DIR, exist_ok=True)
    count = build_store(storage.DEFAULT_FILE)
    build_store(storage.SAMPLE_JSON)

    csv_rows = [[name, roll, category, description, priority, filed, status, closed, note]
                for name, roll, category, priority, status, filed, closed, description, note in RECORDS]
    write_csv(os.path.join(storage.DATA_DIR, "sample_complaints.csv"), csv_rows)
    write_csv(storage.SAMPLE_IMPORT, LEGACY_ROWS)
    print(f"Wrote {count} sample complaints (database, JSON and CSV) and the demo import file to {storage.DATA_DIR}")


if __name__ == "__main__":
    main()
