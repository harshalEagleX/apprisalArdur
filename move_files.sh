#!/bin/bash
set -e

# Move Common
mv src/main/java/com/apprisal/entity/* common/src/main/java/com/apprisal/entity/ || true
mv src/main/java/com/apprisal/repository/* common/src/main/java/com/apprisal/repository/ || true
mv src/main/java/com/apprisal/dto/* common/src/main/java/com/apprisal/dto/ || true
mv src/main/java/com/apprisal/exception/* common/src/main/java/com/apprisal/exception/ || true

# Move Auth
mv src/main/java/com/apprisal/security/* auth/src/main/java/com/apprisal/security/ || true
mv src/main/java/com/apprisal/service/AuthenticationService.java auth/src/main/java/com/apprisal/service/ || true
mv src/main/java/com/apprisal/service/UserPrincipal.java auth/src/main/java/com/apprisal/service/ || true
mv src/main/java/com/apprisal/controller/AuthController.java auth/src/main/java/com/apprisal/controller/ || true

# Move Admin
mv src/main/java/com/apprisal/controller/AdminController.java admin/src/main/java/com/apprisal/controller/ || true
mv src/main/java/com/apprisal/controller/api/AdminApiController.java admin/src/main/java/com/apprisal/controller/api/ || true
mv src/main/java/com/apprisal/service/UserService.java admin/src/main/java/com/apprisal/service/ || true
mv src/main/java/com/apprisal/service/ClientService.java admin/src/main/java/com/apprisal/service/ || true
mv src/main/java/com/apprisal/service/ImpersonationService.java admin/src/main/java/com/apprisal/service/ || true

# Move Client
mv src/main/java/com/apprisal/controller/ClientController.java client/src/main/java/com/apprisal/controller/ || true

# Move Reviewer
mv src/main/java/com/apprisal/controller/ReviewerController.java reviewer/src/main/java/com/apprisal/controller/ || true
mv src/main/java/com/apprisal/service/VerificationService.java reviewer/src/main/java/com/apprisal/service/ || true

# Move Batch
mv src/main/java/com/apprisal/controller/api/BatchApiController.java batch/src/main/java/com/apprisal/controller/api/ || true
mv src/main/java/com/apprisal/controller/FileController.java batch/src/main/java/com/apprisal/controller/ || true
mv src/main/java/com/apprisal/service/BatchService.java batch/src/main/java/com/apprisal/service/ || true
mv src/main/java/com/apprisal/service/QCProcessingService.java batch/src/main/java/com/apprisal/service/ || true
mv src/main/java/com/apprisal/service/PythonClientService.java batch/src/main/java/com/apprisal/service/ || true
mv src/main/java/com/apprisal/service/FileMatchingService.java batch/src/main/java/com/apprisal/service/ || true

# Move Application
mkdir -p application/src/main/java/com/apprisal/service
mv src/main/java/com/apprisal/config/* application/src/main/java/com/apprisal/config/ || true
mv src/main/java/com/apprisal/ApprisalApplication.java application/src/main/java/com/apprisal/ || true
mv src/main/java/com/apprisal/controller/PageController.java application/src/main/java/com/apprisal/controller/ || true
mv src/main/java/com/apprisal/controller/ProfileController.java application/src/main/java/com/apprisal/controller/ || true
mv src/main/java/com/apprisal/service/DashboardService.java application/src/main/java/com/apprisal/service/ || true
mv src/main/resources/* application/src/main/resources/ || true
mv src/main/java/com/apprisal/util application/src/main/java/com/apprisal/ || true

echo "Files moved successfully."
