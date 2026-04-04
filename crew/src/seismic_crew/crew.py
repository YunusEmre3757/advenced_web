from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task


# 70b for fault analysis (scientific quality)
GROQ_LLM = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.2,
    max_tokens=1200,
)

# 8b for data collection and report writing (fast, high TPM limit)
GROQ_LLM_FAST = LLM(
    model="groq/llama-3.1-8b-instant",
    temperature=0.1,
    max_tokens=800,
)


@CrewBase
class SeismicCrew:
    """SeismicCrew — multi-agent seismic analysis pipeline for Turkey.

    Agents
    ------
    data_collector   : fetches earthquake + fault data from backend API
    fault_analyst    : correlates events with active faults, assigns hazard level
    risk_assessor    : builds city-level risk matrix using soil classification data
    report_writer    : compiles a bilingual (TR/EN) situation report → report.md

    Process: sequential (data → fault → risk → report)
    """

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    # ------------------------------------------------------------------ agents

    @agent
    def data_collector(self) -> Agent:
        return Agent(
            config=self.agents_config["data_collector"],
            llm=GROQ_LLM,
            verbose=True,
        )

    @agent
    def fault_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["fault_analyst"],
            llm=GROQ_LLM,
            verbose=True,
        )

    @agent
    def risk_assessor(self) -> Agent:
        return Agent(
            config=self.agents_config["risk_assessor"],
            llm=GROQ_LLM,
            verbose=True,
        )

    @agent
    def report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["report_writer"],
            llm=GROQ_LLM,
            verbose=True,
        )

    # ------------------------------------------------------------------- tasks

    @task
    def collect_data_task(self) -> Task:
        return Task(
            config=self.tasks_config["collect_data_task"],
        )

    @task
    def fault_analysis_task(self) -> Task:
        return Task(
            config=self.tasks_config["fault_analysis_task"],
        )

    @task
    def risk_assessment_task(self) -> Task:
        return Task(
            config=self.tasks_config["risk_assessment_task"],
        )

    @task
    def write_report_task(self) -> Task:
        return Task(
            config=self.tasks_config["write_report_task"],
            output_file="report.md",
        )

    # -------------------------------------------------------------------- crew

    @crew
    def crew(self) -> Crew:
        """Assemble the SeismicCrew with sequential process."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
