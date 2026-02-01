"""
Software Architect Agent

Responsible for system design and technology decisions.
"""

from langchain_core.messages import AIMessage

from .base import BaseAgent, get_llm, load_prompts, create_prompt_template
from ..state import DevTeamState


class ArchitectAgent(BaseAgent):
    """Software Architect agent for system design."""
    
    def __init__(self):
        prompts = load_prompts("architect")
        llm = get_llm(role="architect", temperature=0.7)
        super().__init__(name="architect", llm=llm, prompts=prompts)
    
    def design_architecture(self, state: DevTeamState) -> dict:
        """
        Design the system architecture based on requirements.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["architecture_design"]
        )
        
        chain = prompt | self.llm
        
        requirements = state.get("requirements", [])
        user_stories = state.get("user_stories", [])
        
        response = chain.invoke({
            "task": state["task"],
            "requirements": "\n".join(f"- {r}" for r in requirements),
            "user_stories": "\n".join(str(s) for s in user_stories) if user_stories else "None provided",
        })
        
        content = response.content
        
        # Check if approval is needed
        # For MVP, we'll auto-approve, but this could trigger HITL
        needs_approval = False  # Set to True to enable HITL for architecture
        
        if needs_approval:
            return {
                "messages": [AIMessage(content=content, name="architect")],
                "current_agent": "architect",
                "needs_clarification": True,
                "clarification_question": f"Please review the proposed architecture:\n\n{content}\n\nDo you approve? (yes/no with feedback)",
                "clarification_context": "Architecture review",
            }
        
        # Extract tech stack (simplified)
        tech_stack = []
        if "python" in content.lower():
            tech_stack.append("Python")
        if "react" in content.lower():
            tech_stack.append("React")
        if "typescript" in content.lower():
            tech_stack.append("TypeScript")
        if "fastapi" in content.lower():
            tech_stack.append("FastAPI")
        if "postgresql" in content.lower() or "postgres" in content.lower():
            tech_stack.append("PostgreSQL")
        
        return {
            "messages": [AIMessage(content=content, name="architect")],
            "architecture": {"design": content},
            "tech_stack": tech_stack if tech_stack else ["Python"],
            "current_agent": "architect",
            "next_agent": "developer",
            "needs_clarification": False,
        }
    
    def create_implementation_spec(self, state: DevTeamState) -> dict:
        """
        Create detailed implementation specification for developers.
        """
        prompt = create_prompt_template(
            self.system_prompt,
            self.prompts["implementation_spec"]
        )
        
        chain = prompt | self.llm
        
        architecture = state.get("architecture", {})
        
        response = chain.invoke({
            "task": state["task"],
            "architecture": architecture.get("design", "Not specified"),
            "file_structure": "To be determined based on architecture",
            "code_guidelines": "Follow best practices for the chosen stack",
            "important_notes": "Ensure code is well-documented and tested",
        })
        
        return {
            "messages": [AIMessage(content=response.content, name="architect")],
            "architecture": {
                **architecture,
                "implementation_spec": response.content,
            },
        }


# Create singleton instance
_architect_agent = None


def get_architect_agent() -> ArchitectAgent:
    """Get or create the Architect agent instance."""
    global _architect_agent
    if _architect_agent is None:
        _architect_agent = ArchitectAgent()
    return _architect_agent


def architect_agent(state: DevTeamState) -> dict:
    """
    Architect agent node function for LangGraph.
    """
    agent = get_architect_agent()
    
    # If clarification response received, continue with design
    if state.get("clarification_response"):
        # Process approval and continue
        return agent.design_architecture(state)
    
    # Design architecture
    return agent.design_architecture(state)
