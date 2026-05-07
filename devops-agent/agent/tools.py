from langchain_core.tools import tool


@tool
def explain_gitops_concept(concept: str) -> str:
    """Jelaskan konsep GitOps seperti: flux, argocd, reconciliation, drift detection, pull vs push deployment."""
    knowledge = {
        "flux": (
            "Flux adalah GitOps operator untuk Kubernetes. "
            "Flux menggunakan pull-based model: controller di dalam cluster memantau Git repo "
            "dan secara otomatis menerapkan perubahan ke cluster. "
            "Komponen: Source Controller, Kustomize Controller, Helm Controller, Notification Controller."
        ),
        "argocd": (
            "Argo CD adalah declarative GitOps CD tool untuk Kubernetes. "
            "Fitur: UI web, multi-cluster, SSO, RBAC, app-of-apps pattern, ApplicationSet. "
            "Sync policy: manual atau automatic. Health status: Healthy/Degraded/Progressing/Suspended."
        ),
        "reconciliation": (
            "Reconciliation adalah proses di mana GitOps operator membandingkan desired state (Git) "
            "dengan actual state (cluster) dan melakukan koreksi bila ada drift. "
            "Loop: Observe → Diff → Act. Frekuensi default Flux: setiap 1 menit."
        ),
        "drift detection": (
            "Drift terjadi ketika actual state cluster berbeda dengan desired state di Git. "
            "Penyebab: manual kubectl apply, patch darurat, atau perubahan eksternal. "
            "Solusi: enable auto-remediation di ArgoCD (syncPolicy.automated) atau Flux."
        ),
        "pull vs push": (
            "Push-based: pipeline CI/CD (Jenkins, GitHub Actions) mengirim perubahan langsung ke cluster via kubectl/helm. "
            "Pull-based (GitOps): agent di cluster menarik perubahan dari Git secara periodik. "
            "Pull lebih aman karena cluster credentials tidak disimpan di CI/CD."
        ),
    }
    key = concept.lower()
    for k, v in knowledge.items():
        if k in key:
            return v
    return (
        f"Konsep '{concept}' dalam GitOps: GitOps menggunakan Git sebagai single source of truth "
        "untuk infrastruktur dan aplikasi. Prinsip: declarative, versioned, automated, continuously reconciled."
    )


@tool
def explain_kubernetes_resource(resource: str) -> str:
    """Jelaskan Kubernetes resource atau konsep: pod, deployment, service, ingress, hpa, pvc, configmap, secret, namespace, rbac, networkpolicy."""
    knowledge = {
        "pod": "Unit terkecil di K8s. Berisi 1+ container yang berbagi network namespace dan storage. Lifecycle: Pending→Running→Succeeded/Failed.",
        "deployment": "Mengelola ReplicaSet untuk rolling update, rollback, dan scaling stateless apps. Strategi: RollingUpdate (default) atau Recreate.",
        "service": "Abstraksi jaringan untuk mengakses pod. Tipe: ClusterIP (internal), NodePort, LoadBalancer, ExternalName.",
        "ingress": "Layer 7 routing ke services. Butuh Ingress Controller (nginx, traefik, istio). Support TLS termination, path/host based routing.",
        "hpa": "Horizontal Pod Autoscaler: scale pod berdasarkan CPU/memory atau custom metrics. Needs metrics-server. min/max replicas + targetUtilization.",
        "pvc": "PersistentVolumeClaim: request storage oleh pod. Terikat ke PersistentVolume. StorageClass menentukan provisioner (EBS, NFS, Ceph).",
        "configmap": "Menyimpan konfigurasi non-sensitif sebagai key-value. Bisa di-mount sebagai file atau env var.",
        "secret": "Seperti ConfigMap tapi untuk data sensitif. Disimpan base64-encoded (bukan encrypted by default). Gunakan Sealed Secrets atau External Secrets Operator.",
        "namespace": "Virtual cluster untuk isolasi resource. Default namespaces: default, kube-system, kube-public. Gunakan untuk multi-tenant atau environment separation.",
        "rbac": "Role-Based Access Control. Objek: Role/ClusterRole (permissions) + RoleBinding/ClusterRoleBinding (assignment). Prinsip least privilege.",
        "networkpolicy": "Firewall rules antar pod. Default: semua traffic diizinkan. NetworkPolicy membatasi ingress/egress berdasarkan podSelector, namespaceSelector, ipBlock.",
    }
    key = resource.lower()
    for k, v in knowledge.items():
        if k in key:
            return v
    return f"Resource Kubernetes '{resource}': Kubernetes adalah container orchestration platform open-source. Gunakan 'kubectl explain {resource}' untuk dokumentasi resmi."


@tool
def explain_cicd_pattern(pattern: str) -> str:
    """Jelaskan pola CI/CD: pipeline stages, github actions, jenkins, tekton, helm, kustomize, canary, blue-green, rollback."""
    knowledge = {
        "github actions": (
            "GitHub Actions: CI/CD terintegrasi di GitHub. "
            "Struktur: Workflow (.github/workflows/*.yml) → Job → Step. "
            "Trigger: push, pull_request, schedule, workflow_dispatch. "
            "Gunakan reusable workflows dan composite actions untuk DRY. "
            "Secrets disimpan di Settings → Secrets. OIDC untuk auth ke cloud tanpa credentials permanen."
        ),
        "jenkins": (
            "Jenkins: CI/CD server open-source. Jenkinsfile (Declarative atau Scripted Pipeline). "
            "Stages: Checkout → Build → Test → Security Scan → Build Image → Push → Deploy. "
            "Plugin populer: Blue Ocean, Kubernetes Plugin, Docker Pipeline, SonarQube Scanner."
        ),
        "tekton": (
            "Tekton: Cloud-native CI/CD di Kubernetes. Objek: Task → Pipeline → PipelineRun. "
            "Tekton Triggers untuk event-driven pipelines. Tekton Hub untuk reusable tasks. "
            "Cocok dipadukan dengan ArgoCD untuk full GitOps pipeline."
        ),
        "helm": (
            "Helm: package manager untuk Kubernetes. Chart = template + values.yaml. "
            "Commands: helm install, upgrade, rollback, diff (plugin). "
            "Best practice: pisahkan values per environment (values-prod.yaml, values-staging.yaml). "
            "Helm Secrets untuk enkripsi values sensitif."
        ),
        "kustomize": (
            "Kustomize: template-free Kubernetes config management. "
            "Struktur: base/ + overlays/dev|staging|prod. "
            "Fitur: patches, namePrefix/Suffix, commonLabels, configMapGenerator, secretGenerator. "
            "Built-in di kubectl (kubectl apply -k)."
        ),
        "canary": (
            "Canary deployment: rilis ke sebagian kecil traffic dulu (misal 5%). "
            "Implementasi: Argo Rollouts, Flagger + service mesh (Istio/Linkerd), NGINX weighted routing. "
            "Metrics: error rate, latency, custom business metrics → auto-promote atau rollback."
        ),
        "blue-green": (
            "Blue-Green: dua environment identik. Blue = aktif, Green = versi baru. "
            "Switch traffic sekaligus via Service selector atau load balancer. "
            "Zero-downtime, rollback instan (switch balik ke blue). Resource cost 2x."
        ),
        "rollback": (
            "Rollback strategi: "
            "1. Helm: helm rollback <release> <revision> "
            "2. kubectl: kubectl rollout undo deployment/<name> "
            "3. Argo CD: revert commit di Git atau sync ke previous revision "
            "4. Flux: revert commit + force reconcile (flux reconcile)"
        ),
        "pipeline stages": (
            "Typical DevOps pipeline stages: "
            "1. Source: git commit/PR trigger "
            "2. Build: compile, docker build "
            "3. Test: unit, integration, e2e "
            "4. Security: SAST (Semgrep), DAST, container scan (Trivy), secret scan "
            "5. Package: push image ke registry "
            "6. Deploy: update manifest di Git repo (GitOps) atau langsung ke cluster "
            "7. Verify: smoke test, health check "
            "8. Notify: Slack, PagerDuty"
        ),
    }
    key = pattern.lower()
    for k, v in knowledge.items():
        if k in key:
            return v
    return (
        f"Pola CI/CD '{pattern}': CI/CD adalah praktik mengotomasi build, test, dan deploy. "
        "CI = Continuous Integration (merge frequent, test otomatis). "
        "CD = Continuous Delivery/Deployment (deploy otomatis ke staging/prod)."
    )


@tool
def get_kubectl_commands(operation: str) -> str:
    """Berikan contoh perintah kubectl untuk operasi: debug, logs, exec, scale, rollout, port-forward, top, get, describe, apply, delete."""
    commands = {
        "debug": (
            "# Debug pod\n"
            "kubectl debug -it <pod> --image=busybox --target=<container>\n"
            "kubectl debug node/<node> -it --image=ubuntu\n"
            "# Ephemeral container (K8s 1.23+)\n"
            "kubectl debug -it <pod> --image=nicolaka/netshoot --share-processes"
        ),
        "logs": (
            "# Logs dasar\n"
            "kubectl logs <pod> -c <container> --follow\n"
            "kubectl logs <pod> --previous  # container sebelumnya\n"
            "kubectl logs -l app=myapp --all-containers=true --since=1h\n"
            "# Stern (multi-pod logs)\n"
            "stern <app-name> -n <namespace>"
        ),
        "exec": (
            "kubectl exec -it <pod> -- /bin/sh\n"
            "kubectl exec -it <pod> -c <container> -- bash\n"
            "# Run command langsung\n"
            "kubectl exec <pod> -- env | grep MY_VAR"
        ),
        "scale": (
            "kubectl scale deployment <name> --replicas=3\n"
            "kubectl scale --replicas=0 deployment/<name>  # scale down ke 0\n"
            "# HPA override (sementara)\n"
            "kubectl patch hpa <name> -p '{\"spec\":{\"minReplicas\":5}}'"
        ),
        "rollout": (
            "kubectl rollout status deployment/<name>\n"
            "kubectl rollout history deployment/<name>\n"
            "kubectl rollout undo deployment/<name>\n"
            "kubectl rollout undo deployment/<name> --to-revision=2\n"
            "kubectl rollout restart deployment/<name>  # trigger rolling restart"
        ),
        "port-forward": (
            "kubectl port-forward pod/<pod> 8080:80\n"
            "kubectl port-forward svc/<service> 9090:9090\n"
            "kubectl port-forward deployment/<deploy> 5432:5432"
        ),
        "top": (
            "kubectl top nodes\n"
            "kubectl top pods -n <namespace> --sort-by=memory\n"
            "kubectl top pods --containers=true"
        ),
    }
    key = operation.lower()
    for k, v in commands.items():
        if k in key:
            return v
    return (
        f"kubectl {operation}: gunakan 'kubectl {operation} --help' untuk dokumentasi lengkap.\n"
        "Tips umum: tambahkan -n <namespace> untuk namespace spesifik, -A untuk semua namespace, "
        "-o yaml/json/wide untuk output format."
    )


TOOLS = [
    explain_gitops_concept,
    explain_kubernetes_resource,
    explain_cicd_pattern,
    get_kubectl_commands,
]
