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
                    // Detect the branch and apply the correct Docker files
                    if (env.BRANCH_NAME == 'development') {
                        echo "🔨 Branch: development -> Building and Deploying Development Stack (Hot-Reloading)..."
                        sh "docker compose -f docker-compose.yml build"
                        sh "docker compose -f docker-compose.yml up -d"
                    } else if (env.BRANCH_NAME == 'main' || env.BRANCH_NAME == 'master') {
                        echo "🚀 Branch: main/master -> Building and Deploying Production Stack (Immutable)..."
                        sh "docker compose -f docker-compose.prod.yml build"
                        sh "docker compose -f docker-compose.prod.yml up -d"
                    } else {
                        echo "⚠️ Branch: ${env.BRANCH_NAME} -> Unknown branch, building dev stack by default."
                        sh "docker compose -f docker-compose.yml build"
                        sh "docker compose -f docker-compose.yml up -d"
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
