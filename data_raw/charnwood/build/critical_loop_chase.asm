0000000000001629 <chase>:
    1629:	f3 0f 1e fa          	endbr64
    162d:	55                   	push   rbp
    162e:	48 89 e5             	mov    rbp,rsp
    1631:	48 89 7d e8          	mov    QWORD PTR [rbp-0x18],rdi
    1635:	48 89 75 e0          	mov    QWORD PTR [rbp-0x20],rsi
    1639:	48 c7 45 f8 00 00 00 	mov    QWORD PTR [rbp-0x8],0x0
    1640:	00 
    1641:	eb 10                	jmp    1653 <chase+0x2a>
    1643:	48 8b 45 e8          	mov    rax,QWORD PTR [rbp-0x18]
    1647:	48 8b 00             	mov    rax,QWORD PTR [rax]
    164a:	48 89 45 e8          	mov    QWORD PTR [rbp-0x18],rax
    164e:	48 83 45 f8 01       	add    QWORD PTR [rbp-0x8],0x1
    1653:	48 8b 45 f8          	mov    rax,QWORD PTR [rbp-0x8]
    1657:	48 3b 45 e0          	cmp    rax,QWORD PTR [rbp-0x20]
    165b:	72 e6                	jb     1643 <chase+0x1a>
    165d:	48 8b 45 e8          	mov    rax,QWORD PTR [rbp-0x18]
    1661:	5d                   	pop    rbp
    1662:	c3                   	ret
