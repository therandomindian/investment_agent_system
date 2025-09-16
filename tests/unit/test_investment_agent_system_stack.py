import aws_cdk as core
import aws_cdk.assertions as assertions

from investment_agent_system.investment_agent_system_stack import InvestmentAgentSystemStack

# example tests. To run these tests, uncomment this file along with the example
# resource in investment_agent_system/investment_agent_system_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = InvestmentAgentSystemStack(app, "investment-agent-system")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
