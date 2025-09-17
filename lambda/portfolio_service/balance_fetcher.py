# lambda/portfolio_service/balance_fetcher.py

import json
import boto3
import urllib3
from typing import Dict, Any

# Initialize HTTP client
http = urllib3.PoolManager()

PORTFOLIO_API_ENDPOINT = "https://fh1f7wxye9.execute-api.us-east-1.amazonaws.com/prod/portfolio/balance"

def handler(event, context):
    """
    Lambda function to fetch portfolio balance from external API
    """
    try:
        print(f"Received event: {json.dumps(event, default=str)}")
        
        # Handle case where event might be a list or have different structure
        if isinstance(event, list):
            event = event[0] if event else {}
        
        # Parse the input from the bedrock agent
        function_name = event.get("function", "")
        parameters_list = event.get("parameters", [])
        action_group = event.get("actionGroup", "")
        
        # Convert parameters list to dictionary
        parameters = {}
        if isinstance(parameters_list, list):
            for param in parameters_list:
                if isinstance(param, dict) and "name" in param and "value" in param:
                    parameters[param["name"]] = param["value"]
        
        if function_name != "get_portfolio_balance":
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": action_group,
                    "function": function_name,
                    "functionResponse": {
                        "responseBody": {
                            "TEXT": {
                                "body": f"Error: Unknown function: {function_name}"
                            }
                        }
                    }
                }
            }
        
        # Fetch portfolio balance from external API
        portfolio_data = fetch_portfolio_balance()
        
        if portfolio_data is None:
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": action_group,
                    "function": function_name,
                    "functionResponse": {
                        "responseBody": {
                            "TEXT": {
                                "body": "Sorry, I'm unable to fetch your portfolio balance at the moment. Please try again later."
                            }
                        }
                    }
                }
            }
        
        # Generate response with balance information and investment suggestions
        response_text = generate_balance_response(portfolio_data)
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": action_group,
                "function": function_name,
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": response_text
                        }
                    }
                }
            }
        }
        
    except Exception as e:
        print(f"Error fetching portfolio balance: {e}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "") if isinstance(event, dict) else "",
                "function": function_name if 'function_name' in locals() else "",
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": f"Error fetching portfolio balance: {str(e)}"
                        }
                    }
                }
            }
        }


def fetch_portfolio_balance() -> Dict[str, Any] | None:
    """
    Fetch portfolio balance from the external API
    """
    try:
        response = http.request('GET', PORTFOLIO_API_ENDPOINT)
        
        if response.status == 200:
            data = json.loads(response.data.decode('utf-8'))
            return data
        else:
            print(f"API request failed with status: {response.status}")
            return None
            
    except Exception as e:
        print(f"Error calling portfolio API: {e}")
        return None


def generate_balance_response(portfolio_data: Dict[str, Any]) -> str:
    """
    Generate a formatted response with portfolio balance and investment suggestions
    """
    try:
        portfolio = portfolio_data.get('portfolio', {})
        total_value = portfolio.get('totalValue', 0)
        cash_balance = portfolio.get('cashBalance', 0)
        currency = portfolio.get('currency', 'USD')
        
        # Performance data
        performance = portfolio.get('performance', {})
        twelve_month_return = performance.get('twelveMonths', {}).get('percentReturn', 0)
        
        # Asset allocation
        summary = portfolio.get('summary', {})
        day_change = summary.get('dayChange', 0)
        day_change_percent = summary.get('dayChangePercent', 0)
        
        # Build response
        response_parts = []
        
        # Main balance information
        response_parts.append(f"Here's your current portfolio summary:")
        response_parts.append(f"• Total Portfolio Value: ${total_value:,.2f} {currency}")
        response_parts.append(f"• Available Cash Balance: ${cash_balance:,.2f} {currency}")
        response_parts.append(f"• Today's Change: ${day_change:,.2f} ({day_change_percent:+.2f}%)")
        response_parts.append(f"• 12-Month Return: {twelve_month_return:+.2f}%")
        
        # Investment suggestion if there's excess cash
        if cash_balance > 0:
            response_parts.append("")
            response_parts.append("💡 **Investment Opportunity:**")
            response_parts.append(f"I notice you have ${cash_balance:,.2f} in cash sitting in your account. ")
            
            if cash_balance > 1000:
                response_parts.append("This represents a good opportunity to deploy this capital into your investment strategy. ")
                response_parts.append("Consider:")
                response_parts.append("• Dollar-cost averaging into your existing holdings")
                response_parts.append("• Rebalancing your portfolio to maintain your target allocation")
                response_parts.append("• Investing in diversified index funds if you're looking for broad market exposure")
            else:
                response_parts.append("While this amount is relatively small, every dollar invested has the potential to grow over time. ")
                response_parts.append("Consider adding it to your regular investment positions.")
            
            response_parts.append("")
            response_parts.append("Remember: Time in the market tends to be more beneficial than timing the market. ")
            response_parts.append("However, please consider your own financial goals and risk tolerance before making any investment decisions.")
        
        # Top holdings summary
        positions = portfolio.get('positions', [])
        if positions:
            response_parts.append("")
            response_parts.append("**Top Holdings:**")
            # Show top 3 positions by value
            sorted_positions = sorted(positions, key=lambda x: x.get('totalValue', 0), reverse=True)
            for i, position in enumerate(sorted_positions[:3]):
                symbol = position.get('symbol', 'N/A')
                name = position.get('name', 'N/A')
                total_value = position.get('totalValue', 0)
                gain_loss_percent = position.get('gainLossPercent', 0)
                response_parts.append(f"{i+1}. {symbol} - ${total_value:,.2f} ({gain_loss_percent:+.2f}%)")
        
        return "\n".join(response_parts)
        
    except Exception as e:
        print(f"Error generating response: {e}")
        return f"I was able to fetch your portfolio data, but encountered an issue formatting the response. Your total portfolio value is ${portfolio_data.get('portfolio', {}).get('totalValue', 0):,.2f}."