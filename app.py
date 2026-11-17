"""Study Plan Generator (LLM Mini Project, PS25)

Takes subjects + syllabus + exam date + hours/day, counts the days left in
Python, and asks an LLM (Gemini) to build a day-wise study timetable.
"""
import json
import os
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
MODEL = "gemini-3.1-flash-lite"


def parse_syllabus(text: str) -> dict:
    """Parse lines like 'Maths: algebra, calculus' into {subject: [topics]}."""
    subjects = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, topics = line.split(":", 1)
        name = name.strip()
        topic_list = [t.strip() for t in topics.split(",") if t.strip()]
        if name and topic_list:
            subjects[name] = topic_list
    return subjects


def build_prompt(today, exam_date, days_left, hours, subjects, weak, revision_days):
    syllabus = "\n".join(f"- {s}: {', '.join(t)}" for s, t in subjects.items())
    weak_txt = ", ".join(weak) if weak else "none"
    return f"""You are an expert study planner.
Today is {today.isoformat()}. The exam is on {exam_date.isoformat()} ({days_left} days from today).
The student can study {hours} hours per day.

Subjects and topics:
{syllabus}

Weak subjects (give these more time): {weak_txt}

Rules:
1. Create exactly one entry per subject block per day, from today until the day before the exam.
2. Total hours on any single day must not exceed {hours}.
3. Cover every topic at least once.
4. Put harder/larger subjects earlier and mix subjects to avoid fatigue.
5. Reserve the last {revision_days} day(s) purely for revision (subject = "Revision").

Return ONLY a JSON list. Each item must have these keys:
"day" (int), "date" (YYYY-MM-DD), "subject" (str), "topics" (str), "hours" (number)."""


def generate_plan(prompt: str, api_key: str) -> pd.DataFrame:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(response.text)
    df = pd.DataFrame(data)
    cols = ["day", "date", "subject", "topics", "hours"]
    return df[[c for c in cols if c in df.columns]]


st.set_page_config(page_title="Study Plan Generator", page_icon="📚")
st.title("📚 Study Plan Generator")
st.caption("Enter your subjects and exam date to get a day-wise study timetable.")

api_key = os.getenv("GEMINI_API_KEY") or st.sidebar.text_input(
    "Gemini API key", type="password"
)

syllabus_text = st.text_area(
    "Subjects and topics (one subject per line, format: Subject: topic1, topic2)",
    value="Maths: algebra, calculus, probability\nPhysics: mechanics, optics, thermodynamics\nChemistry: organic, inorganic",
    height=150,
)
col1, col2, col3 = st.columns(3)
exam_date = col1.date_input("Exam date", value=date.today() + timedelta(days=14))
hours = col2.number_input("Study hours per day", 1, 16, 4)
revision_days = col3.number_input("Revision days at end", 0, 7, 2)

subjects = parse_syllabus(syllabus_text)
weak = st.multiselect("Weak subjects (get more time)", list(subjects.keys()))

if st.button("Generate plan", type="primary"):
    days_left = (exam_date - date.today()).days
    if not api_key:
        st.error("Please provide a Gemini API key.")
    elif not subjects:
        st.error("Add at least one subject in the format 'Subject: topic1, topic2'.")
    elif days_left <= 0:
        st.error("The exam date must be in the future.")
    elif revision_days >= days_left:
        st.error(f"Only {days_left} day(s) left; reduce revision days.")
    else:
        total_hours = days_left * hours
        st.info(f"{days_left} days left, {total_hours} total study hours available.")
        if days_left <= 2:
            st.warning("Very little time left: the plan will be a quick crash schedule.")
        prompt = build_prompt(date.today(), exam_date, days_left, hours, subjects, weak, revision_days)
        try:
            with st.spinner("Building your plan..."):
                plan = generate_plan(prompt, api_key)
            st.dataframe(plan, use_container_width=True, hide_index=True)
            if "hours" in plan.columns:
                st.caption(f"Planned hours: {pd.to_numeric(plan['hours'], errors='coerce').sum():g}")
            st.download_button(
                "Download CSV", plan.to_csv(index=False), "study_plan.csv", "text/csv"
            )
        except json.JSONDecodeError:
            st.error("The model returned invalid JSON. Please click Generate again.")
        except Exception as e:
            st.error(f"Something went wrong: {e}")
