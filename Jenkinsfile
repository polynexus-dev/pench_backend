pipeline {
    agent any

    environment {
        // Optional container registry credentials
        REGISTRY = "docker.io"
        IMAGE_NAME = "polynexus/pench-backend"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build & Deploy Stack') {
            steps {
                script {
                    // Single production docker-compose configuration
                    if (env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'master' || env.BRANCH_NAME == 'development') {
                        echo "🚀 Building and Deploying Production Stack..."
                        sh "docker compose build"
                        sh "docker compose up -d"
                    } else {
                        echo "⚠️ Branch: ${env.BRANCH_NAME} -> building stack."
                        sh "docker compose build"
                        sh "docker compose up -d"
                    }
                }
            }
        }
    }

    post {
        success {
            echo "✅ Jenkins build and deployment completed successfully for branch: ${env.BRANCH_NAME}!"
        }
        failure {
            echo "❌ Build failed. Please check the Jenkins console output logs."
        }
    }
}
