"""Read-only explanations from accepted authenticated manual practice records."""
import re


def explain_manual(manager, user, agent, question):
    match = re.search(r'manual trade ID ([a-f0-9-]{32,36})', question, re.I)
    trade = None if 'unsubmitted' in question.lower() else manager.manual_trade_source(user.user_id, match.group(1) if match else None)
    evidence = []
    if trade:
        answer = (f"Your recorded manual practice trade: {trade['side']} {trade['quantity']:.8f} {trade['symbol']}.\n"
                  f"Recorded at {trade['timestamp']}. Modeled fill ${trade['fill_price']:.6f}; notional ${trade['notional']:.2f}.\n"
                  f"Fee ${trade['fee']:.2f}; slippage cost ${trade['slippage_cost']:.2f}; realized P&L ${trade['realized_pnl']:.2f}.\n\n"
                  "You initiated this paper trade. The recorded execution does not establish your reason for trading. "
                  "Manual practice balances remain separate from autonomous agents. "
                  "Comparing strategy rationale requires a specific recorded agent decision.")
        evidence = [{'type':'manual_trade','id':trade['trade_id'],'label':'Recorded manual practice trade','href':'/test/manual'}]
    else:
        answer = 'No matching accepted manual trade is recorded for your account. An unsubmitted preview is not an executed trade.'
    message = manager.store.add_message(user.user_id, agent, 'assistant', answer, evidence)
    return {'message':message,'evidence':evidence,'explanation_provider':{'provider':'grounded-local','routing':'manual-record'},
            'provider_error':None,'paper_only':True,'live_trading_enabled':False}
