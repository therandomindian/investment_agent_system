# investment_agent_system/investment_agent_system_stack.py

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    CfnParameter, 
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_apigateway as apigateway,
    aws_bedrock as bedrock,
    aws_s3 as s3,
    aws_logs as logs,
    CustomResource,
    custom_resources as cr
)
from constructs import Construct
from aws_cdk.aws_lambda import Architecture
from aws_cdk.aws_lambda_python_alpha import PythonFunction

class InvestmentAgentSystemStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Hardcoded Knowledge Base ID
        knowledge_base_id = "2MONVUTDYX"

        # S3 Bucket for PDS documents
        pds_bucket = s3.Bucket(
            self, "PdsDocumentsBucket",
            versioned=False, # Versioning is now turned off
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL
        )

        # IAM Role for Bedrock Agents to run
        agent_execution_role = iam.Role(
            self, "BedrockAgentExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )
        agent_execution_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-micro-v1:0"]
        ))

        # Grant the agent role permission to retrieve from the manually created KB
        agent_execution_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "bedrock:Retrieve",
                "bedrock:RetrieveAndGenerate",
                "bedrock:GetKnowledgeBase",
                "bedrock:ListKnowledgeBases"
            ],
            resources=[
                f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/{knowledge_base_id}",
                f"arn:aws:bedrock:{self.region}:{self.account}:knowledge-base/{knowledge_base_id}/*"
            ]
        ))

        # Portfolio Balance Service Lambda
        portfolio_balance_lambda = PythonFunction(
            self, "PortfolioBalanceLambda",
            entry="lambda/portfolio_service",
            index="balance_fetcher.py", 
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=Architecture.ARM_64,
            timeout=Duration.seconds(30),
        )

        # Bedrock Agents
        personalized_agent = bedrock.CfnAgent(
            self, "PersonalizedInfoAgent",
            agent_name="Personalized-Information-Agent",
            agent_resource_role_arn=agent_execution_role.role_arn,
            foundation_model="amazon.nova-micro-v1:0",
            instruction="""You are a personalized financial assistant that can help users with their portfolio and account information. 

When a user asks about their account balance, portfolio value, or wants to see their current holdings, use the get_portfolio_balance function to fetch their real-time portfolio data. You do not need to ask for an account number or any account identification - the system automatically knows which account to retrieve information for.

You should be helpful and provide relevant insights about their portfolio. When there is unused cash in the portfolio, provide a brief investment suggestion in no more than 2 sentences.

IMPORTANT: When asked about account performance, performance trends, or performance analysis, FIRST use the get_portfolio_balance function to retrieve the current portfolio data, then provide your detailed performance analysis and insights based on that data, followed by chart data.

After completing your text analysis, add a clear delimiter line with "---CHART_DATA---" and then provide ONLY the JSON chart data in the following format:

---CHART_DATA---
{
    "type": "line",
    "title": "Portfolio Performance",
    "xLabel": "Time",
    "yLabel": "Portfolio Value ($)",
    "data": [
      {"x": "Jan", "y": 95000},
      {"x": "Feb", "y": 98000},
      {"x": "Mar", "y": 102000},
      {"x": "Apr", "y": 105000}
    ],
    "colors": ["#4A5568"]
}

CRITICAL: After the JSON chart data, do NOT add any additional text, explanations, or content. The response must end immediately after the closing brace of the JSON object.

Populate the chart data with realistic performance data based on the portfolio information retrieved. Use appropriate time periods (months, quarters, or years) and realistic portfolio values that reflect actual performance trends.

For non-performance queries, respond normally with helpful portfolio insights and include investment disclaimers as appropriate.""",
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="PortfolioService",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=portfolio_balance_lambda.function_arn
                    ),
                    function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                        functions=[
                            bedrock.CfnAgent.FunctionProperty(
                                name="get_portfolio_balance",
                                description="Fetch the user's current portfolio balance, holdings, and performance data",
                                parameters={}
                            )
                        ]
                    )
                )
            ]
        )

        general_agent = bedrock.CfnAgent(
            self, "GeneralAdviceAgent",
            agent_name="General-Advice-Agent",
            agent_resource_role_arn=agent_execution_role.role_arn,
            foundation_model="amazon.nova-micro-v1:0",
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                knowledge_base_id=knowledge_base_id,
                description="Contains Product Disclosure Statements (PDS) for Vanguard Australia products."
            )],
            instruction=""" You are an expert AI assistant representing Vanguard Investments Australia. Your primary role is to provide factual, educational information and general financial advice to clients based strictly on official Vanguard documentation.

                            **Core Directives:**

                            1.  **Source of Truth:** You MUST base all answers about Vanguard's products, their features, performance, and fees exclusively on the content retrieved from the knowledge base (the provided S3 vector store). Do not invent information or use your general training data for product-specific queries. If the answer to a user's question cannot be found in the provided documents, you MUST state that the information is not available in the official documents you have access to.

                            2.  **General Advice Only:** You are operating under Australian Financial Services Law and are ONLY permitted to provide General Advice. This is a strict and critical constraint. General Advice does not take into account a person's individual objectives, financial situation, or needs.
                                - NEVER recommend that a user should buy, sell, or hold a specific product.
                                - NEVER suggest a product is suitable or a good fit for a user.
                                - Your role is to explain what products are and how they work in a factual, objective way, based on the documents. For example, instead of saying "You should consider this ETF for growth," say "This ETF aims to provide capital growth by investing in a portfolio of Australian shares."

                            3.  **Tone:** Your tone must be professional, objective, helpful, and aligned with Vanguard's brand of providing clear, straightforward investment information.

                            **Mandatory Output Format:**

                            CRITICAL: Every single response you generate MUST begin with the following "General Advice Warning," formatted exactly as shown below in a markdown block. There are no exceptions to this rule.

                            ---
                            > **General Advice Warning**
                            > The information provided is general in nature and does not take into account your personal objectives, financial situation, or needs. You should consider your own circumstances and whether the information is appropriate for you before making any investment decision. We recommend you seek independent financial advice.
                            ---

                            After providing this warning, proceed to answer the user's query according to the directives above.
                            """,
        )

        # Detailed Investment Advice Agent
        detailed_investment_agent = bedrock.CfnAgent(
            self, "DetailedInvestmentAgent",
            agent_name="Detailed-Investment-Agent", 
            agent_resource_role_arn=agent_execution_role.role_arn,
            foundation_model="amazon.nova-micro-v1:0",
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                knowledge_base_id=knowledge_base_id,
                description="Contains Product Disclosure Statements (PDS) for Vanguard Australia products."
            )],
            instruction="""You are an expert financial advisor specializing in detailed investment strategy and analysis. Your role is to provide comprehensive investment advice, cash deployment strategies, and what-if scenario analysis.

**Core Expertise Areas:**
1. **Cash Investment Strategies:** Provide detailed recommendations on how to deploy available cash across different asset classes, considering risk tolerance, time horizons, and market conditions.

2. **What-If Scenario Analysis:** Analyze hypothetical investment scenarios, portfolio rebalancing strategies, and the potential impact of market changes on investment outcomes.

3. **Strategic Investment Planning:** Offer insights on asset allocation, diversification strategies, and long-term wealth building approaches.

4. **Market Analysis:** Provide context on current market conditions and how they might affect investment decisions.

**Key Directives:**
- Always provide comprehensive, well-reasoned investment analysis
- Consider multiple perspectives and risk factors
- Use data from the knowledge base when discussing specific Vanguard products
- Provide actionable insights for cash deployment and portfolio optimization
- Address both opportunities and risks in your recommendations

**Mandatory Output Format:**
Every response MUST begin with the following General Advice Warning:

---
> **General Advice Warning**
> The information provided is general in nature and does not take into account your personal objectives, financial situation, or needs. You should consider your own circumstances and whether the information is appropriate for you before making any investment decision. We recommend you seek independent financial advice.
---

**Response Guidelines:**
- For cash investment queries, provide specific allocation strategies with rationale
- For what-if scenarios, analyze multiple potential outcomes with probability assessments where relevant  
- Include considerations for market timing, dollar-cost averaging, and risk management
- Suggest appropriate Vanguard products based on the investment objectives discussed
- Always emphasize the importance of diversification and long-term thinking

Your advice should be detailed, strategic, and actionable while maintaining compliance with General Advice requirements.""",
        )

        # Create agent aliases (required for invocation)
        personalized_agent_alias = bedrock.CfnAgentAlias(
            self, "PersonalizedAgentAlias",
            agent_alias_name="PersonalizedAgentAlias",
            agent_id=personalized_agent.attr_agent_id
        )
        
        general_agent_alias = bedrock.CfnAgentAlias(
            self, "GeneralAgentAlias", 
            agent_alias_name="GeneralAgentAlias",
            agent_id=general_agent.attr_agent_id
        )

        detailed_investment_agent_alias = bedrock.CfnAgentAlias(
            self, "DetailedInvestmentAgentAlias",
            agent_alias_name="DetailedInvestmentAgentAlias", 
            agent_id=detailed_investment_agent.attr_agent_id
        )

        # Router Lambda functions are no longer needed with agent collaboration
        # The main agent will directly collaborate with specialist agents
        # 
        # # Create Lambda functions for agent routing (after aliases are created)
        # personalized_router_lambda = PythonFunction(
        #     self, "PersonalizedRouterLambda",
        #     entry="lambda/agent_router",
        #     index="personalized_router.py",
        #     handler="handler",
        #     runtime=_lambda.Runtime.PYTHON_3_11,
        #     architecture=Architecture.ARM_64,
        #     timeout=Duration.seconds(90),
        #     environment={
        #         "AGENT_ID": personalized_agent.attr_agent_id,
        #         "AGENT_ALIAS_ID": "SIEATICOXG"
        #     }
        # )
        # 
        # general_router_lambda = PythonFunction(
        #     self, "GeneralRouterLambda", 
        #     entry="lambda/agent_router",
        #     index="general_router.py",
        #     handler="handler",
        #     runtime=_lambda.Runtime.PYTHON_3_11,
        #     architecture=Architecture.ARM_64,
        #     timeout=Duration.seconds(90),
        #     environment={
        #         "AGENT_ID": general_agent.attr_agent_id,
        #         "AGENT_ALIAS_ID": general_agent_alias.attr_agent_alias_id
        #     }
        # )
        #
        # detailed_investment_router_lambda = PythonFunction(
        #     self, "DetailedInvestmentRouterLambda",
        #     entry="lambda/agent_router",
        #     index="detailed_investment_router.py", 
        #     handler="handler",
        #     runtime=_lambda.Runtime.PYTHON_3_11,
        #     architecture=Architecture.ARM_64,
        #     timeout=Duration.seconds(90),
        #     environment={
        #         "AGENT_ID": detailed_investment_agent.attr_agent_id,
        #         "AGENT_ALIAS_ID": detailed_investment_agent_alias.attr_agent_alias_id
        #     }
        # )
        # personalized_router_lambda.role.add_to_policy(iam.PolicyStatement(
        #     actions=["bedrock:InvokeAgent"],
        #     resources=[f"arn:aws:bedrock:{self.region}:{self.account}:agent-alias/{personalized_agent.attr_agent_id}/*"]
        # ))
        # 
        # general_router_lambda.role.add_to_policy(iam.PolicyStatement(
        #     actions=["bedrock:InvokeAgent"],
        #     resources=[f"arn:aws:bedrock:{self.region}:{self.account}:agent-alias/{general_agent.attr_agent_id}/*"]
        # ))
        #
        # detailed_investment_router_lambda.role.add_to_policy(iam.PolicyStatement(
        #     actions=["bedrock:InvokeAgent"],
        #     resources=[f"arn:aws:bedrock:{self.region}:{self.account}:agent-alias/{detailed_investment_agent.attr_agent_id}/*"]
        # ))

        # Grant the agent role permission to collaborate with other agents
        agent_execution_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeAgent"],
            resources=[f"arn:aws:bedrock:{self.region}:{self.account}:agent/*", 
                      f"arn:aws:bedrock:{self.region}:{self.account}:agent-alias/*/*"]
        ))

        # Main Investment Agent with Collaboration Capabilities
        main_investment_agent = bedrock.CfnAgent(
            self, "MainInvestmentAgent",
            agent_name="Main-Investment-Agent",
            agent_resource_role_arn=agent_execution_role.role_arn,
            foundation_model="amazon.nova-micro-v1:0",
            instruction="""You are a master financial query orchestrator. Your job is to route queries to the correct specialist agent.
                
                You have access to two functions:
                - invoke_personalized_agent: Use this for personal financial questions, account-specific queries, or questions about the user's individual situation
                - invoke_general_agent: Use this for general market information, product explanations, or educational content about investments
                
                Analyze the user's query and determine which agent would be most appropriate. Then call the corresponding function with the user's query.
                Return only the response from the specialist agent.""",
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                knowledge_base_id=knowledge_base_id,
                description="Contains Product Disclosure Statements (PDS) for Vanguard Australia products."
            )]
        )
        
        # Create main agent alias
        main_agent_alias = bedrock.CfnAgentAlias(
            self, "MainInvestmentAgentAlias",
            agent_alias_name="MainInvestmentAgentAlias", 
            agent_id=main_investment_agent.attr_agent_id
        )
        
        # Router Lambda permissions no longer needed with agent collaboration
        # # Grant Lambda functions permission to be invoked by Bedrock
        # personalized_router_lambda.add_permission(
        #     "BedrockInvokePermission",
        #     principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
        #     action="lambda:InvokeFunction"
        # )
        # 
        # general_router_lambda.add_permission(
        #     "BedrockInvokePermission", 
        #     principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
        #     action="lambda:InvokeFunction"
        # )
        #
        # detailed_investment_router_lambda.add_permission(
        #     "BedrockInvokePermission",
        #     principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
        #     action="lambda:InvokeFunction"
        # )
        
        # Portfolio lambda permission is granted below with a specific identifier
        
        # --- THE FIX ---
        # Explicitly define the Log Group for the Lambda function to prevent conflicts
        invoke_agent_log_group = logs.LogGroup(
            self, "InvokeAgentLambdaLogGroup",
            # A unique but predictable name for the log group
            log_group_name=f"/aws/lambda/{self.stack_name}-InvokeAgentLambda",
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # API Entrypoint Lambda
        invoke_agent_lambda = PythonFunction(
            self, "InvokeAgentLambda",
            entry="lambda/invoke_agent",
            index="app.py",
            handler="handler",
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=Architecture.ARM_64,
            timeout=Duration.seconds(90),
            environment={
                "MAIN_AGENT_ID": main_investment_agent.attr_agent_id,
                "MAIN_AGENT_ALIAS_ID": main_agent_alias.attr_agent_alias_id
            },
            # Associate the explicitly created log group
            log_group=invoke_agent_log_group
        )
        
        invoke_agent_lambda.role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeAgent"],
            resources=[
                f"arn:aws:bedrock:{self.region}:{self.account}:agent-alias/{main_investment_agent.attr_agent_id}/*"
            ]
        ))

        # Grant portfolio lambda permission to be invoked by the main agent
        portfolio_balance_lambda.add_permission(
            "MainAgentInvokePermission",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction"
        )

        # Add outputs for the new agent aliases
        CfnOutput(self, "PersonalizedAgentId", value=personalized_agent.attr_agent_id)
        CfnOutput(self, "GeneralAgentId", value=general_agent.attr_agent_id) 
        CfnOutput(self, "DetailedInvestmentAgentId", value=detailed_investment_agent.attr_agent_id)
        CfnOutput(self, "MainInvestmentAgentId", value=main_investment_agent.attr_agent_id)
        CfnOutput(self, "PersonalizedAgentAliasId", value=personalized_agent_alias.attr_agent_alias_id)
        CfnOutput(self, "GeneralAgentAliasId", value=general_agent_alias.attr_agent_alias_id)
        CfnOutput(self, "DetailedInvestmentAgentAliasId", value=detailed_investment_agent_alias.attr_agent_alias_id)
        CfnOutput(self, "MainInvestmentAgentAliasId", value=main_agent_alias.attr_agent_alias_id)

        # API Gateway with public access and logging
        api_log_group = logs.LogGroup(self, "ApiAccessLogs")
        api = apigateway.LambdaRestApi(
            self, "InvestmentAgentApi",
            handler=invoke_agent_lambda,
            deploy_options=apigateway.StageOptions(
                access_log_destination=apigateway.LogGroupLogDestination(api_log_group),
                access_log_format=apigateway.AccessLogFormat.json_with_standard_fields(
                    caller=True, http_method=True, ip=True, protocol=True, request_time=True,
                    resource_path=True, response_length=True, status=True, user=True
                )
            )
        )
        
        # Outputs
        CfnOutput(self, "ApiEndpointUrl", value=api.url)
        CfnOutput(self, "PdsBucketName", value=pds_bucket.bucket_name)