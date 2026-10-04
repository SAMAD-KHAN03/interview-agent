"""
Pydantic schemas shared by the token server, the agent and Gemini.

These double as Gemini `response_schema`s, so every field has a description
that tells the model what to put there.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Resume
# --------------------------------------------------------------------------- #
class ExperienceItem(BaseModel):
    company: str = Field(description="Employer or organisation name")
    role: str = Field(description="Job title / role")
    duration: str = Field(description="Time span as written in the resume, or empty string")
    highlights: list[str] = Field(description="Key responsibilities or achievements, copied or condensed from the resume")


class ProjectItem(BaseModel):
    name: str = Field(description="Project name")
    description: str = Field(description="What the project does, as described in the resume")
    technologies: list[str] = Field(description="Technologies, languages, frameworks mentioned for this project")
    highlights: list[str] = Field(description="Notable outcomes, metrics or contributions mentioned")


class EducationItem(BaseModel):
    institution: str
    degree: str = Field(description="Degree / programme, or empty string")
    duration: str = Field(description="Time span as written in the resume, or empty string")


class ResumeProfile(BaseModel):
    candidate_name: str = Field(description="Candidate's full name, or empty string if not present")
    headline: str = Field(description="One-line professional summary of the candidate based only on the resume")
    skills: list[str] = Field(description="Technical skills explicitly listed or clearly used in the resume")
    experience: list[ExperienceItem]
    projects: list[ProjectItem]
    education: list[EducationItem]
    claims_worth_probing: list[str] = Field(
        description=(
            "3-6 specific claims in the resume an interviewer should verify "
            "(e.g. 'Reduced API latency by 40%', 'Led a team of 5'). Only claims actually stated in the resume."
        )
    )


# --------------------------------------------------------------------------- #
# Interview report (result screen)
# --------------------------------------------------------------------------- #
class Metric(BaseModel):
    score: int = Field(ge=1, le=10, description="Score from 1 (very weak) to 10 (excellent)")
    explanation: str = Field(description="1-2 sentences justifying the score, referring to what the candidate actually said")


class TopicScore(BaseModel):
    topic: str = Field(description="A topic that was discussed in the interview (e.g. 'State management', 'Testing')")
    score: int = Field(ge=1, le=10)
    comment: str = Field(description="One sentence on how well the candidate handled this topic")


class InterviewReport(BaseModel):
    overall_rating: int = Field(ge=1, le=10, description="Overall interview performance from 1 to 10")
    summary: str = Field(description="2-3 sentence overall assessment")
    clarity: Metric = Field(description="How clearly and logically the candidate explained topics")
    responsiveness: Metric = Field(
        description="How directly and completely the candidate's answers addressed the questions that were asked"
    )
    technical_depth: Metric = Field(description="Depth and correctness of the technical content in the answers")
    resume_consistency: Metric = Field(
        description="How well the candidate's answers matched and could back up what the resume claims"
    )
    topics: list[TopicScore] = Field(description="Per-topic breakdown for the topics actually discussed")
    strengths: list[str] = Field(description="Specific strengths, each tied to something said in the interview")
    improvements: list[str] = Field(description="Specific areas to improve, each tied to something said in the interview")
    practice_suggestions: list[str] = Field(description="Concrete things the candidate can practise before a real interview")


class ReportSubmission(BaseModel):
    """Body the agent POSTs to the token server when the interview ends."""

    report: Optional[InterviewReport] = None
    error: Optional[str] = None


class ReportResponse(BaseModel):
    status: Literal["pending", "ready", "failed"]
    report: Optional[InterviewReport] = None
    error: Optional[str] = None
