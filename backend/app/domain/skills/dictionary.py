"""
Curated skill alias dictionary.

Maps normalized alias strings to (canonical_name, category). This is the
fast path in Phase 7's hybrid resolver: anything found here is resolved
instantly, for free, with perfect reproducibility — no LLM call needed.

Keys must already be normalized (see normalizer.py's _normalize_key) —
lowercase, single-spaced, no periods.
"""
from app.domain.entities.skill import SkillCategory

# (canonical_name, category) -> tuple of aliases (normalized-key form).
# Written this way so adding a new skill means one line, not scattered
# dictionary entries.
_SKILL_GROUPS: list[tuple[str, SkillCategory, tuple[str, ...]]] = [
    # --- Programming ---
    ("Python", SkillCategory.PROGRAMMING, ("python", "py", "python3")),
    ("JavaScript", SkillCategory.PROGRAMMING, ("javascript", "js", "java script")),
    ("TypeScript", SkillCategory.PROGRAMMING, ("typescript", "ts", "type script")),
    ("C++", SkillCategory.PROGRAMMING, ("c++", "c plus plus", "cpp")),
    ("C", SkillCategory.PROGRAMMING, ("c", "c programming")),
    ("C#", SkillCategory.PROGRAMMING, ("c#", "c sharp", "csharp")),
    ("Java", SkillCategory.PROGRAMMING, ("java",)),
    ("Go", SkillCategory.PROGRAMMING, ("go", "golang")),
    ("Rust", SkillCategory.PROGRAMMING, ("rust",)),
    ("Ruby", SkillCategory.PROGRAMMING, ("ruby", "ruby on rails", "rails")),
    ("PHP", SkillCategory.PROGRAMMING, ("php",)),
    ("Swift", SkillCategory.PROGRAMMING, ("swift",)),
    ("Kotlin", SkillCategory.PROGRAMMING, ("kotlin",)),
    ("Scala", SkillCategory.PROGRAMMING, ("scala",)),
    ("R", SkillCategory.PROGRAMMING, ("r", "r language", "r programming")),
    ("MATLAB", SkillCategory.PROGRAMMING, ("matlab",)),
    ("Bash", SkillCategory.PROGRAMMING, ("bash", "shell scripting", "shell script", "sh")),
    ("HTML", SkillCategory.PROGRAMMING, ("html", "html5")),
    ("CSS", SkillCategory.PROGRAMMING, ("css", "css3")),
    ("React", SkillCategory.PROGRAMMING, ("react", "reactjs", "react js")),
    ("Vue.js", SkillCategory.PROGRAMMING, ("vue", "vuejs", "vue js")),
    ("Angular", SkillCategory.PROGRAMMING, ("angular", "angularjs")),
    ("Node.js", SkillCategory.PROGRAMMING, ("nodejs", "node js", "node")),
    ("Django", SkillCategory.PROGRAMMING, ("django",)),
    ("FastAPI", SkillCategory.PROGRAMMING, ("fastapi", "fast api")),
    ("Flask", SkillCategory.PROGRAMMING, ("flask",)),
    ("Spring Boot", SkillCategory.PROGRAMMING, ("spring boot", "springboot", "spring")),
    # --- Cloud ---
    ("AWS", SkillCategory.CLOUD, ("aws", "amazon web services")),
    ("Azure", SkillCategory.CLOUD, ("azure", "microsoft azure")),
    ("GCP", SkillCategory.CLOUD, ("gcp", "google cloud", "google cloud platform")),
    ("Docker", SkillCategory.CLOUD, ("docker", "containerization")),
    ("Kubernetes", SkillCategory.CLOUD, ("kubernetes", "k8s")),
    ("Terraform", SkillCategory.CLOUD, ("terraform", "iac", "infrastructure as code")),
    ("CloudFormation", SkillCategory.CLOUD, ("cloudformation", "aws cloudformation")),
    ("Serverless", SkillCategory.CLOUD, ("serverless", "serverless framework")),
    ("Lambda", SkillCategory.CLOUD, ("lambda", "aws lambda")),
    ("EC2", SkillCategory.CLOUD, ("ec2", "aws ec2")),
    ("S3", SkillCategory.CLOUD, ("s3", "aws s3")),
    # --- Databases ---
    ("PostgreSQL", SkillCategory.DATABASES, ("postgresql", "postgres", "postgre sql")),
    ("MySQL", SkillCategory.DATABASES, ("mysql", "my sql")),
    ("MongoDB", SkillCategory.DATABASES, ("mongodb", "mongo", "mongo db")),
    ("Redis", SkillCategory.DATABASES, ("redis",)),
    ("SQLite", SkillCategory.DATABASES, ("sqlite", "sq lite")),
    ("Oracle", SkillCategory.DATABASES, ("oracle", "oracle db", "oracle database")),
    ("SQL Server", SkillCategory.DATABASES, ("sql server", "microsoft sql server", "mssql")),
    ("Cassandra", SkillCategory.DATABASES, ("cassandra", "apache cassandra")),
    ("DynamoDB", SkillCategory.DATABASES, ("dynamodb", "dynamo db")),
    ("Elasticsearch", SkillCategory.DATABASES, ("elasticsearch", "elastic search")),
    ("Neo4j", SkillCategory.DATABASES, ("neo4j",)),
    ("SQL", SkillCategory.DATABASES, ("sql", "structured query language")),
    ("NoSQL", SkillCategory.DATABASES, ("nosql", "no sql")),
    # --- AI ---
    ("Machine Learning", SkillCategory.AI, ("machine learning", "ml")),
    ("Deep Learning", SkillCategory.AI, ("deep learning", "dl")),
    ("TensorFlow", SkillCategory.AI, ("tensorflow", "tensor flow")),
    ("PyTorch", SkillCategory.AI, ("pytorch", "py torch")),
    ("Scikit-learn", SkillCategory.AI, ("scikit learn", "sklearn", "scikit-learn")),
    ("NLP", SkillCategory.AI, ("nlp", "natural language processing")),
    ("Computer Vision", SkillCategory.AI, ("computer vision", "cv")),
    ("LangChain", SkillCategory.AI, ("langchain", "lang chain")),
    ("Hugging Face", SkillCategory.AI, ("hugging face", "huggingface")),
    ("Keras", SkillCategory.AI, ("keras",)),
    ("Pandas", SkillCategory.AI, ("pandas",)),
    ("NumPy", SkillCategory.AI, ("numpy", "num py")),
    # --- DevOps ---
    ("CI/CD", SkillCategory.DEVOPS, ("ci/cd", "cicd", "ci cd", "continuous integration")),
    ("Jenkins", SkillCategory.DEVOPS, ("jenkins",)),
    ("GitHub Actions", SkillCategory.DEVOPS, ("github actions", "gh actions")),
    ("GitLab CI", SkillCategory.DEVOPS, ("gitlab ci", "gitlab")),
    ("Ansible", SkillCategory.DEVOPS, ("ansible",)),
    ("Puppet", SkillCategory.DEVOPS, ("puppet",)),
    ("Chef", SkillCategory.DEVOPS, ("chef",)),
    ("Prometheus", SkillCategory.DEVOPS, ("prometheus",)),
    ("Grafana", SkillCategory.DEVOPS, ("grafana",)),
    ("Nginx", SkillCategory.DEVOPS, ("nginx",)),
    ("Linux", SkillCategory.DEVOPS, ("linux", "unix")),
    ("Git", SkillCategory.DEVOPS, ("git", "version control")),
    # --- Soft Skills ---
    ("Communication", SkillCategory.SOFT_SKILLS, ("communication", "communication skills")),
    ("Leadership", SkillCategory.SOFT_SKILLS, ("leadership",)),
    ("Teamwork", SkillCategory.SOFT_SKILLS, ("teamwork", "team work", "team player")),
    ("Problem Solving", SkillCategory.SOFT_SKILLS, ("problem solving", "problem-solving")),
    ("Time Management", SkillCategory.SOFT_SKILLS, ("time management",)),
    ("Adaptability", SkillCategory.SOFT_SKILLS, ("adaptability", "flexibility")),
    ("Critical Thinking", SkillCategory.SOFT_SKILLS, ("critical thinking",)),
    ("Collaboration", SkillCategory.SOFT_SKILLS, ("collaboration",)),
    ("Mentoring", SkillCategory.SOFT_SKILLS, ("mentoring", "mentorship")),
    ("Public Speaking", SkillCategory.SOFT_SKILLS, ("public speaking", "presentation skills")),
]


def _build_lookup() -> dict[str, tuple[str, SkillCategory]]:
    lookup: dict[str, tuple[str, SkillCategory]] = {}
    for canonical_name, category, aliases in _SKILL_GROUPS:
        for alias in aliases:
            lookup[alias] = (canonical_name, category)
    return lookup


SKILL_LOOKUP: dict[str, tuple[str, SkillCategory]] = _build_lookup()
