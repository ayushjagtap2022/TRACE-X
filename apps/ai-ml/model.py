from trace_x_schemas.models import Account

def build_feature_row(account: Account) -> dict:
	return {
		"account_id": account.account_id,
		"risk_category": account.risk_category,
		"kyc_tier": account.kyc_tier,
		"txn_count_30d": account.txn_count_30d,
	}

if __name__ == "__main__":
	print("model")