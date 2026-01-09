# Workshop Cleanup

After completing the workshop, run the cleanup script to remove all AWS resources.

## Usage

```bash
cd cleanup
python cleanup.py
```

## Resources Removed

The cleanup script will delete:

1. **DynamoDB Tables**
   - ecommerce-workshop-orders
   - ecommerce-workshop-accounts
   - ecommerce-workshop-products

2. **Bedrock Knowledge Base**
   - Product catalog knowledge base
   - Associated S3 bucket

3. **AgentCore Resources**
   - Runtime deployment
   - ECR repository

4. **IAM Resources**
   - Execution role and policies

5. **CloudWatch Resources**
   - Log groups

## Manual Cleanup

If the script fails, you can manually delete resources:

1. **AgentCore Runtime**: AWS Console → Bedrock → AgentCore → Runtimes
2. **ECR**: AWS Console → ECR → Repositories
3. **DynamoDB**: AWS Console → DynamoDB → Tables
4. **S3**: AWS Console → S3 → Buckets
5. **IAM**: AWS Console → IAM → Roles
6. **CloudWatch**: AWS Console → CloudWatch → Log groups

## Important

- Run cleanup from the same AWS account/region used for the workshop
- Some resources may take several minutes to fully delete
- Check for any failed deletions in the script output
