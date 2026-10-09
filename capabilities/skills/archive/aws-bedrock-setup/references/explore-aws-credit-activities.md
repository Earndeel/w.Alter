# Explore AWS Credit Activities — CLI Recipes

All commands below target `«secret:vault»`. Each activity awards a $20 credit within minutes.

## Activity 1: EC2 Instance

```bash
AMI=$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=al2023-ami-2023*-x86_64" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

SUBNET=$(aws ec2 describe-subnets \
  --filters "Name=default-for-az,Values=true" \
  --query 'Subnets[0].SubnetId' --output text)

aws ec2 run-instances --image-id $AMI --instance-type t3.micro \
  --subnet-id $SUBNET \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=free-tier-test}]'

# Cleanup
aws ec2 terminate-instances --instance-ids <id>
```

## Activity 2: Budget

```bash
aws budgets create-budget \
  --account-id «secret:vault» \
  --budget '{
    "BudgetName": "explore-aws-budget",
    "BudgetLimit": {"Amount": "100", "Unit": "USD"},
    "TimeUnit": "MONTHLY",
    "BudgetType": "COST"
  }'

# Cleanup
aws budgets delete-budget --account-id «secret:vault» --budget-name explore-aws-budget
```

## Activity 3: Bedrock Model

```bash
aws bedrock-runtime invoke-model \
  --model-id "anthropic.claude-haiku-4-5-20251001-v1:0" \
  --region «secret:vault» \
  --content-type "application/json" \
  --accept "application/json" \
  --body '{"anthropic_version":"bedrock-2023-05-31","max_tokens":10,"messages":[{"role":"user","content":"Say OK"}]}' \
  /tmp/bedrock_test.json
```

No cleanup needed.

## Activity 4: RDS Database

```bash
aws rds create-db-instance \
  --db-instance-identifier explore-aws-db \
  --db-instance-class db.t3.micro \
  --engine mysql \
  --master-user-admin admin \
  --master-user-password TempPass123! \
  --allocated-storage 20

# Wait ~2 min for credit, then cleanup IMMEDIATELY
aws rds delete-db-instance \
  --db-instance-identifier explore-aws-db \
  --skip-final-snapshot
```

## Activity 5: Lambda Function

```bash
# 1. Create IAM role
cat > /tmp/lambda-trust.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "lambda.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name explore-aws-lambda-role \
  --assume-role-policy-document file:///tmp/lambda-trust.json

aws iam attach-role-policy \
  --role-name explore-aws-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# 2. Wait for role propagation (10s)
sleep 10

# 3. Create deployment package
echo 'def handler(event, context): return {"statusCode": 200, "body": "OK"}' > /tmp/lambda_function.py
cd /tmp && zip lambda_function.zip lambda_function.py

# 4. Create function
aws lambda create-function \
  --function-name explore-aws-function \
  --runtime python3.12 \
  --role arn:aws:iam::«secret:vault»:role/explore-aws-lambda-role \
  --handler lambda_function.handler \
  --zip-file fileb:///tmp/lambda_function.zip \
  --timeout 30 --memory-size 128

# 5. Invoke once
aws lambda invoke --function-name explore-aws-function --payload '{}' /tmp/lambda_response.json

# 6. Wait ~2 min for credit, then cleanup
aws lambda delete-function --function-name explore-aws-function
aws iam detach-role-policy --role-name explore-aws-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name explore-aws-lambda-role
```

## Verification

Check credits at: `https://us-east-1.console.aws.amazon.com/billing/home#/credits`

Or via CLI (data availability lag ~24h):
```bash
aws ce get-cost-and-usage --region «secret:vault» \
  --time-period Start=2026-06-10,End=2026-06-11 \
  --granularity MONTHLY --metrics "UnblendedCost"
```

Expected: 5 × $20 Explore AWS credits + $100 Free Tier = **$200 total**.
