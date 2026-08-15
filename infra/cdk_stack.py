"""Minimal AWS CDK sketch for the BioLead API (documentation / starting point).

This is not wired into a full CDK app. It shows the intended ECS/ALB shape
that pairs with a Vercel-hosted Next.js frontend.
"""

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from constructs import Construct


class BioLeadApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(self, "BioLeadVpc", max_azs=2)

        cluster = ecs.Cluster(self, "BioLeadCluster", vpc=vpc)

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "BioLeadApiService",
            cluster=cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            public_load_balancer=True,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset("../services/api"),
                container_port=8000,
                environment={
                    "CORS_ORIGINS": "https://your-app.vercel.app",
                },
            ),
            health_check_grace_period=Duration.seconds(60),
        )

        service.target_group.configure_health_check(path="/health")

        CfnOutput(self, "ApiUrl", value=service.load_balancer.load_balancer_dns_name)
        CfnOutput(
            self,
            "VercelEnvHint",
            value="Set NEXT_PUBLIC_API_URL to https://<ApiUrl>",
        )
