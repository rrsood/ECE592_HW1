	.file	"cache_bench.c"
	.text
.Ltext0:
	.file 0 "/home/rrsood/ECE592_HW1" "/home/rrsood/ECE592_HW1/main_code/x86_64/cache_bench.c"
	.type	tsc_start, @function
tsc_start:
.LFB4373:
	.file 1 "/home/rrsood/ECE592_HW1/main_code/x86_64/cache_bench.c"
	.loc 1 293 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	movq	%rdi, -24(%rbp)
.LBB12:
.LBB13:
	.file 2 "/usr/lib/gcc/x86_64-redhat-linux/11/include/emmintrin.h"
	.loc 2 1528 3
	lfence
	.loc 2 1529 1
	nop
	movq	-24(%rbp), %rax
	movq	%rax, -16(%rbp)
.LBE13:
.LBE12:
.LBB14:
.LBB15:
	.file 3 "/usr/lib/gcc/x86_64-redhat-linux/11/include/ia32intrin.h"
	.loc 3 124 10
	rdtscp
	movl	%ecx, %esi
	movq	-16(%rbp), %rcx
	movl	%esi, (%rcx)
	salq	$32, %rdx
	orq	%rdx, %rax
.LBE15:
.LBE14:
	.loc 1 307 9
	movq	%rax, -8(%rbp)
.LBB16:
.LBB17:
	.loc 2 1528 3
	lfence
	.loc 2 1529 1
	nop
.LBE17:
.LBE16:
	.loc 1 315 12
	movq	-8(%rbp), %rax
	.loc 1 316 1
	popq	%rbp
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4373:
	.size	tsc_start, .-tsc_start
	.type	tsc_stop, @function
tsc_stop:
.LFB4374:
	.loc 1 319 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	movq	%rdi, -24(%rbp)
	movq	-24(%rbp), %rax
	movq	%rax, -16(%rbp)
.LBB18:
.LBB19:
	.loc 3 124 10
	rdtscp
	movl	%ecx, %esi
	movq	-16(%rbp), %rcx
	movl	%esi, (%rcx)
	salq	$32, %rdx
	orq	%rdx, %rax
.LBE19:
.LBE18:
	.loc 1 324 9
	movq	%rax, -8(%rbp)
.LBB20:
.LBB21:
	.loc 2 1528 3
	lfence
	.loc 2 1529 1
	nop
.LBE21:
.LBE20:
	.loc 1 330 12
	movq	-8(%rbp), %rax
	.loc 1 331 1
	popq	%rbp
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4374:
	.size	tsc_stop, .-tsc_stop
	.local	g_rng_state
	.comm	g_rng_state,4,4
	.type	xorshift32, @function
xorshift32:
.LFB4375:
	.loc 1 363 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	.loc 1 364 14
	movl	g_rng_state(%rip), %eax
	movl	%eax, -4(%rbp)
	.loc 1 365 12
	movl	-4(%rbp), %eax
	sall	$13, %eax
	.loc 1 365 7
	xorl	%eax, -4(%rbp)
	.loc 1 366 12
	movl	-4(%rbp), %eax
	shrl	$17, %eax
	.loc 1 366 7
	xorl	%eax, -4(%rbp)
	.loc 1 367 12
	movl	-4(%rbp), %eax
	sall	$5, %eax
	.loc 1 367 7
	xorl	%eax, -4(%rbp)
	.loc 1 368 17
	movl	-4(%rbp), %eax
	movl	%eax, g_rng_state(%rip)
	.loc 1 369 12
	movl	-4(%rbp), %eax
	.loc 1 370 1
	popq	%rbp
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4375:
	.size	xorshift32, .-xorshift32
	.type	rng_below_or_equal, @function
rng_below_or_equal:
.LFB4376:
	.loc 1 380 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	subq	$24, %rsp
	movl	%edi, -20(%rbp)
	.loc 1 381 14
	movl	-20(%rbp), %eax
	addl	$1, %eax
	movl	%eax, -4(%rbp)
	.loc 1 382 8
	cmpl	$0, -4(%rbp)
	jne	.L10
	.loc 1 382 31 discriminator 1
	call	xorshift32
	jmp	.L11
.L10:
	.loc 1 384 47
	movl	$-1, %eax
	movl	$0, %edx
	divl	-4(%rbp)
	movl	%edx, %eax
	.loc 1 384 14
	notl	%eax
	movl	%eax, -8(%rbp)
.L12:
	.loc 1 387 13 discriminator 1
	call	xorshift32
	movl	%eax, -12(%rbp)
	.loc 1 388 16 discriminator 1
	movl	-12(%rbp), %eax
	cmpl	-8(%rbp), %eax
	jnb	.L12
	.loc 1 389 14
	movl	-12(%rbp), %eax
	movl	$0, %edx
	divl	-4(%rbp)
	movl	%edx, %eax
.L11:
	.loc 1 390 1
	leave
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4376:
	.size	rng_below_or_equal, .-rng_below_or_equal
	.section	.rodata
	.align 8
.LC0:
	.string	"ERROR: aligned_alloc failed for %zu bytes\n"
	.align 8
.LC1:
	.string	"ERROR: malloc failed for %zu-entry permutation\n"
	.text
	.type	build_ring, @function
build_ring:
.LFB4377:
	.loc 1 417 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	subq	$144, %rsp
	movq	%rdi, -104(%rbp)
	movq	%rsi, -112(%rbp)
	movl	%edx, -116(%rbp)
	movq	%rcx, -128(%rbp)
	movq	%r8, -136(%rbp)
	.loc 1 418 12
	movq	-104(%rbp), %rax
	imulq	-112(%rbp), %rax
	movq	%rax, -32(%rbp)
	.loc 1 435 49
	movq	-32(%rbp), %rax
	addq	$4095, %rax
	.loc 1 435 12
	andq	$-4096, %rax
	movq	%rax, -40(%rbp)
	.loc 1 438 26
	movq	-40(%rbp), %rax
	movq	%rax, %rsi
	movl	$4096, %edi
	call	aligned_alloc
	movq	%rax, -48(%rbp)
	.loc 1 439 8
	cmpq	$0, -48(%rbp)
	jne	.L14
	.loc 1 443 9
	movq	stderr(%rip), %rax
	movq	-40(%rbp), %rdx
	movl	$.LC0, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 444 9
	movl	$1, %edi
	call	exit
.L14:
	.loc 1 462 5
	movq	-40(%rbp), %rdx
	movq	-48(%rbp), %rax
	movl	$0, %esi
	movq	%rax, %rdi
	call	memset
	.loc 1 466 21
	movq	-104(%rbp), %rax
	salq	$3, %rax
	movq	%rax, %rdi
	call	malloc
	movq	%rax, -56(%rbp)
	.loc 1 467 8
	cmpq	$0, -56(%rbp)
	jne	.L15
	.loc 1 468 9
	movq	stderr(%rip), %rax
	movq	-104(%rbp), %rdx
	movl	$.LC1, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 470 9
	movl	$1, %edi
	call	exit
.L15:
.LBB22:
	.loc 1 472 17
	movq	$0, -8(%rbp)
	.loc 1 472 5
	jmp	.L16
.L17:
	.loc 1 472 49 discriminator 3
	movq	-8(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rax, %rdx
	.loc 1 472 53 discriminator 3
	movq	-8(%rbp), %rax
	movq	%rax, (%rdx)
	.loc 1 472 40 discriminator 3
	addq	$1, -8(%rbp)
.L16:
	.loc 1 472 26 discriminator 1
	movq	-8(%rbp), %rax
	cmpq	-104(%rbp), %rax
	jb	.L17
.LBE22:
	.loc 1 474 8
	cmpl	$0, -116(%rbp)
	jne	.L18
.LBB23:
	.loc 1 492 21
	movq	-104(%rbp), %rax
	subq	$1, %rax
	movq	%rax, -16(%rbp)
	.loc 1 492 9
	jmp	.L19
.L20:
.LBB24:
	.loc 1 493 27 discriminator 3
	movq	-16(%rbp), %rax
	movl	%eax, %edi
	call	rng_below_or_equal
	movl	%eax, -60(%rbp)
	.loc 1 494 33 discriminator 3
	movq	-16(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 494 22 discriminator 3
	movq	(%rax), %rax
	movq	%rax, -72(%rbp)
	.loc 1 495 33 discriminator 3
	movl	-60(%rbp), %eax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 495 18 discriminator 3
	movq	-16(%rbp), %rdx
	leaq	0(,%rdx,8), %rcx
	movq	-56(%rbp), %rdx
	addq	%rcx, %rdx
	.loc 1 495 33 discriminator 3
	movq	(%rax), %rax
	.loc 1 495 26 discriminator 3
	movq	%rax, (%rdx)
	.loc 1 496 18 discriminator 3
	movl	-60(%rbp), %eax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rax, %rdx
	.loc 1 496 26 discriminator 3
	movq	-72(%rbp), %rax
	movq	%rax, (%rdx)
.LBE24:
	.loc 1 492 48 discriminator 3
	subq	$1, -16(%rbp)
.L19:
	.loc 1 492 42 discriminator 1
	cmpq	$0, -16(%rbp)
	jne	.L20
.L18:
.LBE23:
.LBB25:
	.loc 1 511 17
	movq	$0, -24(%rbp)
	.loc 1 511 5
	jmp	.L21
.L22:
.LBB26:
	.loc 1 512 28 discriminator 3
	movq	-24(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 512 16 discriminator 3
	movq	(%rax), %rax
	movq	%rax, -80(%rbp)
	.loc 1 513 32 discriminator 3
	movq	-24(%rbp), %rax
	addq	$1, %rax
	.loc 1 513 38 discriminator 3
	movl	$0, %edx
	divq	-104(%rbp)
	movq	%rdx, %rax
	.loc 1 513 28 discriminator 3
	leaq	0(,%rax,8), %rdx
	movq	-56(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 513 16 discriminator 3
	movq	(%rax), %rax
	movq	%rax, -88(%rbp)
	.loc 1 515 43 discriminator 3
	movq	-80(%rbp), %rax
	imulq	-112(%rbp), %rax
	movq	%rax, %rdx
	.loc 1 515 16 discriminator 3
	movq	-48(%rbp), %rax
	addq	%rdx, %rax
	movq	%rax, -96(%rbp)
	.loc 1 516 43 discriminator 3
	movq	-88(%rbp), %rax
	imulq	-112(%rbp), %rax
	movq	%rax, %rdx
	.loc 1 516 36 discriminator 3
	movq	-48(%rbp), %rax
	addq	%rax, %rdx
	.loc 1 516 21 discriminator 3
	movq	-96(%rbp), %rax
	movq	%rdx, (%rax)
.LBE26:
	.loc 1 511 40 discriminator 3
	addq	$1, -24(%rbp)
.L21:
	.loc 1 511 26 discriminator 1
	movq	-24(%rbp), %rax
	cmpq	-104(%rbp), %rax
	jb	.L22
.LBE25:
	.loc 1 519 5
	movq	-56(%rbp), %rax
	movq	%rax, %rdi
	call	free
	.loc 1 525 22
	movq	-128(%rbp), %rax
	movq	-48(%rbp), %rdx
	movq	%rdx, (%rax)
	.loc 1 526 22
	movq	-136(%rbp), %rax
	movq	-40(%rbp), %rdx
	movq	%rdx, (%rax)
	.loc 1 528 12
	movq	-48(%rbp), %rax
	.loc 1 529 1
	leave
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4377:
	.size	build_ring, .-build_ring
	.type	chase, @function
chase:
.LFB4378:
	.loc 1 573 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	movq	%rdi, -24(%rbp)
	movq	%rsi, -32(%rbp)
.LBB27:
	.loc 1 574 19
	movq	$0, -8(%rbp)
	.loc 1 574 5
	jmp	.L25
.L26:
	.loc 1 575 11 discriminator 3
	movq	-24(%rbp), %rax
	movq	(%rax), %rax
	movq	%rax, -24(%rbp)
	.loc 1 574 38 discriminator 3
	addq	$1, -8(%rbp)
.L25:
	.loc 1 574 28 discriminator 1
	movq	-8(%rbp), %rax
	cmpq	-32(%rbp), %rax
	jb	.L26
.LBE27:
	.loc 1 577 12
	movq	-24(%rbp), %rax
	.loc 1 578 1
	popq	%rbp
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4378:
	.size	chase, .-chase
	.local	g_sink
	.comm	g_sink,8,8
	.section	.rodata
	.align 8
.LC2:
	.string	"usage: %s <working_set_bytes> <node_spacing_bytes> <N_per_batch> <num_samples> <seed> [sequential]\n  sequential: 0 = randomized order (default, primary method)\n              1 = sequential order  (prefetcher control)\n"
	.align 8
.LC3:
	.string	"ERROR: node_spacing_bytes (%zu) must be >= %zu and a multiple of %zu\n"
	.align 8
.LC4:
	.string	"ERROR: working_set_bytes (%zu) must be an exact multiple of node_spacing_bytes (%zu).\n       Nearest valid values: %zu or %zu\n"
	.align 8
.LC5:
	.string	"ERROR: N_per_batch and num_samples must both be > 0\n"
	.align 8
.LC6:
	.string	"ERROR: working set too small -- %zu bytes at spacing %zu yields %zu node(s); at least 2 are needed to form a cycle\n"
	.align 8
.LC7:
	.string	"ERROR: malloc failed for %lu samples (%zu bytes)\n"
	.align 8
.LC8:
	.string	"# cache_bench_metadata_version=1\n"
.LC9:
	.string	"# experiment=capacity\n"
.LC10:
	.string	"# working_set_bytes=%zu\n"
.LC11:
	.string	"# node_spacing_bytes=%zu\n"
.LC12:
	.string	"# num_nodes=%zu\n"
.LC13:
	.string	"# actual_footprint_bytes=%zu\n"
.LC14:
	.string	"# allocated_bytes=%zu\n"
.LC15:
	.string	"# buffer_alignment_bytes=%u\n"
.LC16:
	.string	"# pointer_size_bytes=%zu\n"
.LC17:
	.string	"# N_per_batch=%lu\n"
.LC18:
	.string	"# num_samples_requested=%lu\n"
.LC19:
	.string	"# num_samples_emitted=%lu\n"
.LC20:
	.string	"# warmup_steps=%lu\n"
.LC21:
	.string	"# warmup_laps=%.3f\n"
.LC22:
	.string	"# seed=%u\n"
.LC23:
	.string	"sequential"
.LC24:
	.string	"randomized"
.LC25:
	.string	"# traversal_order=%s\n"
.LC26:
	.string	"none"
.LC27:
	.string	"fisher_yates_xorshift32"
.LC28:
	.string	"# shuffle_algorithm=%s\n"
	.align 8
.LC29:
	.string	"# timer_method=lfence;rdtscp;lfence / rdtscp;lfence\n"
.LC30:
	.string	"# timer_units=TSC_ticks\n"
	.align 8
.LC31:
	.string	"# units_note=TSC ticks are NOT core clock cycles; no GHz conversion applied\n"
	.align 8
.LC32:
	.string	"# kernel_type=read_only_pointer_chase\n"
	.align 8
.LC33:
	.string	"# numa_locality_method=first_touch_after_pinning\n"
	.align 8
.LC34:
	.string	"# logical_cpu_from_tsc_aux=%u\n"
	.align 8
.LC35:
	.string	"# migrated_samples_excluded=%lu\n"
.LC36:
	.string	"# sink_ignore=%p\n"
	.align 8
.LC37:
	.string	"sample_index,ticks_elapsed,N_per_batch"
.LC38:
	.string	"%lu,%lu,%lu\n"
	.text
	.globl	main
	.type	main, @function
main:
.LFB4379:
	.loc 1 592 1
	.cfi_startproc
	pushq	%rbp
	.cfi_def_cfa_offset 16
	.cfi_offset 6, -16
	movq	%rsp, %rbp
	.cfi_def_cfa_register 6
	subq	$192, %rsp
	movl	%edi, -180(%rbp)
	movq	%rsi, -192(%rbp)
	.loc 1 593 8
	cmpl	$5, -180(%rbp)
	jg	.L29
	.loc 1 594 9
	movq	-192(%rbp), %rax
	movq	(%rax), %rdx
	movq	stderr(%rip), %rax
	movl	$.LC2, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 600 16
	movl	$1, %eax
	jmp	.L59
.L29:
	.loc 1 603 47
	movq	-192(%rbp), %rax
	addq	$8, %rax
	.loc 1 603 34
	movq	(%rax), %rax
	movl	$10, %edx
	movl	$0, %esi
	movq	%rax, %rdi
	call	strtoull
	movq	%rax, -48(%rbp)
	.loc 1 604 47
	movq	-192(%rbp), %rax
	addq	$16, %rax
	.loc 1 604 34
	movq	(%rax), %rax
	movl	$10, %edx
	movl	$0, %esi
	movq	%rax, %rdi
	call	strtoull
	movq	%rax, -56(%rbp)
	.loc 1 605 47
	movq	-192(%rbp), %rax
	addq	$24, %rax
	.loc 1 605 34
	movq	(%rax), %rax
	movl	$10, %edx
	movl	$0, %esi
	movq	%rax, %rdi
	call	strtoull
	movq	%rax, -64(%rbp)
	.loc 1 606 47
	movq	-192(%rbp), %rax
	addq	$32, %rax
	.loc 1 606 34
	movq	(%rax), %rax
	movl	$10, %edx
	movl	$0, %esi
	movq	%rax, %rdi
	call	strtoull
	movq	%rax, -72(%rbp)
	.loc 1 607 56
	movq	-192(%rbp), %rax
	addq	$40, %rax
	.loc 1 607 44
	movq	(%rax), %rax
	movl	$10, %edx
	movl	$0, %esi
	movq	%rax, %rdi
	call	strtoul
	.loc 1 607 14
	movl	%eax, -76(%rbp)
	.loc 1 608 62
	cmpl	$6, -180(%rbp)
	jle	.L31
	.loc 1 608 57 discriminator 1
	movq	-192(%rbp), %rax
	addq	$48, %rax
	.loc 1 608 48 discriminator 1
	movq	(%rax), %rax
	movq	%rax, %rdi
	call	atoi
	jmp	.L32
.L31:
	.loc 1 608 62 discriminator 2
	movl	$0, %eax
.L32:
	.loc 1 608 14 discriminator 4
	movl	%eax, -80(%rbp)
	.loc 1 616 8 discriminator 4
	cmpq	$7, -56(%rbp)
	jbe	.L33
	.loc 1 616 46 discriminator 1
	movq	-56(%rbp), %rax
	andl	$7, %eax
	.loc 1 616 34 discriminator 1
	testq	%rax, %rax
	je	.L34
.L33:
	.loc 1 617 9
	movq	stderr(%rip), %rax
	movq	-56(%rbp), %rdx
	movl	$8, %r8d
	movl	$8, %ecx
	movl	$.LC3, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 620 16
	movl	$1, %eax
	jmp	.L59
.L34:
	.loc 1 637 28
	movq	-48(%rbp), %rax
	movl	$0, %edx
	divq	-56(%rbp)
	movq	%rdx, %rax
	.loc 1 637 8
	testq	%rax, %rax
	je	.L35
	.loc 1 644 33
	movq	-48(%rbp), %rax
	movl	$0, %edx
	divq	-56(%rbp)
	.loc 1 644 44
	addq	$1, %rax
	.loc 1 638 9
	imulq	-56(%rbp), %rax
	movq	%rax, %rdi
	.loc 1 643 32
	movq	-48(%rbp), %rax
	movl	$0, %edx
	divq	-56(%rbp)
	.loc 1 638 9
	imulq	-56(%rbp), %rax
	movq	%rax, %rsi
	movq	stderr(%rip), %rax
	movq	-56(%rbp), %rcx
	movq	-48(%rbp), %rdx
	movq	%rdi, %r9
	movq	%rsi, %r8
	movl	$.LC4, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 645 16
	movl	$1, %eax
	jmp	.L59
.L35:
	.loc 1 648 8
	cmpq	$0, -64(%rbp)
	je	.L36
	.loc 1 648 26 discriminator 1
	cmpq	$0, -72(%rbp)
	jne	.L37
.L36:
	.loc 1 649 9
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$52, %edx
	movl	$1, %esi
	movl	$.LC5, %edi
	call	fwrite
	.loc 1 650 16
	movl	$1, %eax
	jmp	.L59
.L37:
	.loc 1 654 37
	cmpl	$0, -76(%rbp)
	je	.L38
	.loc 1 654 37 is_stmt 0 discriminator 1
	movl	-76(%rbp), %eax
	jmp	.L39
.L38:
	.loc 1 654 37 discriminator 2
	movl	$1, %eax
.L39:
	.loc 1 654 17 is_stmt 1 discriminator 4
	movl	%eax, g_rng_state(%rip)
	.loc 1 656 12 discriminator 4
	movq	-48(%rbp), %rax
	movl	$0, %edx
	divq	-56(%rbp)
	movq	%rax, -88(%rbp)
	.loc 1 657 8 discriminator 4
	cmpq	$1, -88(%rbp)
	ja	.L40
	.loc 1 658 9
	movq	stderr(%rip), %rax
	movq	-88(%rbp), %rsi
	movq	-56(%rbp), %rcx
	movq	-48(%rbp), %rdx
	movq	%rsi, %r8
	movl	$.LC6, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 662 16
	movl	$1, %eax
	jmp	.L59
.L40:
	.loc 1 668 24
	leaq	-160(%rbp), %rdi
	leaq	-152(%rbp), %rcx
	movl	-80(%rbp), %edx
	movq	-56(%rbp), %rsi
	movq	-88(%rbp), %rax
	movq	%rdi, %r8
	movq	%rax, %rdi
	call	build_ring
	movq	%rax, -96(%rbp)
	.loc 1 670 15
	movq	-152(%rbp), %rax
	movq	%rax, -8(%rbp)
	.loc 1 694 14
	movq	-88(%rbp), %rax
	movq	%rax, -104(%rbp)
	.loc 1 695 14
	movq	-64(%rbp), %rdx
	movq	%rdx, %rax
	salq	$2, %rax
	addq	%rdx, %rax
	addq	%rax, %rax
	movq	%rax, -112(%rbp)
	.loc 1 696 14
	movq	-112(%rbp), %rdx
	movq	-104(%rbp), %rax
	cmpq	%rax, %rdx
	cmovnb	%rdx, %rax
	movq	%rax, -120(%rbp)
	.loc 1 699 14
	movq	-120(%rbp), %rdx
	movq	-8(%rbp), %rax
	movq	%rdx, %rsi
	movq	%rax, %rdi
	call	chase
	movq	%rax, -8(%rbp)
	.loc 1 700 12
	movq	-8(%rbp), %rax
	movq	%rax, g_sink(%rip)
	.loc 1 713 25
	movq	-72(%rbp), %rax
	salq	$3, %rax
	movq	%rax, %rdi
	call	malloc
	movq	%rax, -128(%rbp)
	.loc 1 714 8
	cmpq	$0, -128(%rbp)
	jne	.L41
	.loc 1 715 9
	movq	-72(%rbp), %rax
	leaq	0(,%rax,8), %rcx
	movq	stderr(%rip), %rax
	movq	-72(%rbp), %rdx
	movl	$.LC7, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 718 16
	movl	$1, %eax
	jmp	.L59
.L41:
	.loc 1 746 14
	movl	$0, -12(%rbp)
	.loc 1 747 14
	movq	$0, -24(%rbp)
.LBB28:
	.loc 1 749 19
	movq	$0, -32(%rbp)
	.loc 1 749 5
	jmp	.L42
.L46:
.LBB29:
	.loc 1 752 23
	leaq	-164(%rbp), %rax
	movq	%rax, %rdi
	call	tsc_start
	movq	%rax, -136(%rbp)
	.loc 1 753 23
	movq	-64(%rbp), %rdx
	movq	-8(%rbp), %rax
	movq	%rdx, %rsi
	movq	%rax, %rdi
	call	chase
	movq	%rax, -8(%rbp)
	.loc 1 754 23
	leaq	-168(%rbp), %rax
	movq	%rax, %rdi
	call	tsc_stop
	movq	%rax, -144(%rbp)
	.loc 1 756 16
	movq	-8(%rbp), %rax
	movq	%rax, g_sink(%rip)
	.loc 1 758 12
	cmpq	$0, -32(%rbp)
	jne	.L43
	.loc 1 758 31 discriminator 1
	movl	-164(%rbp), %eax
	movl	%eax, -12(%rbp)
.L43:
	.loc 1 760 19
	movl	-164(%rbp), %edx
	movl	-168(%rbp), %eax
	.loc 1 760 12
	cmpl	%eax, %edx
	je	.L44
	.loc 1 761 20
	movq	-32(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-128(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 761 24
	movq	$-1, (%rax)
	.loc 1 762 29
	addq	$1, -24(%rbp)
	jmp	.L45
.L44:
	.loc 1 764 20
	movq	-32(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-128(%rbp), %rax
	addq	%rax, %rdx
	.loc 1 764 29
	movq	-144(%rbp), %rax
	subq	-136(%rbp), %rax
	.loc 1 764 24
	movq	%rax, (%rdx)
.L45:
.LBE29:
	.loc 1 749 44 discriminator 2
	addq	$1, -32(%rbp)
.L42:
	.loc 1 749 28 discriminator 1
	movq	-32(%rbp), %rax
	cmpq	-72(%rbp), %rax
	jb	.L46
.LBE28:
	.loc 1 779 5
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$33, %edx
	movl	$1, %esi
	movl	$.LC8, %edi
	call	fwrite
	.loc 1 780 5
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$22, %edx
	movl	$1, %esi
	movl	$.LC9, %edi
	call	fwrite
	.loc 1 781 5
	movq	stderr(%rip), %rax
	movq	-48(%rbp), %rdx
	movl	$.LC10, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 782 5
	movq	stderr(%rip), %rax
	movq	-56(%rbp), %rdx
	movl	$.LC11, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 783 5
	movq	stderr(%rip), %rax
	movq	-88(%rbp), %rdx
	movl	$.LC12, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 784 5
	movq	-88(%rbp), %rax
	imulq	-56(%rbp), %rax
	movq	%rax, %rdx
	movq	stderr(%rip), %rax
	movl	$.LC13, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 785 5
	movq	-160(%rbp), %rdx
	movq	stderr(%rip), %rax
	movl	$.LC14, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 786 5
	movq	stderr(%rip), %rax
	movl	$4096, %edx
	movl	$.LC15, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 787 5
	movq	stderr(%rip), %rax
	movl	$8, %edx
	movl	$.LC16, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 788 5
	movq	stderr(%rip), %rax
	movq	-64(%rbp), %rdx
	movl	$.LC17, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 789 5
	movq	stderr(%rip), %rax
	movq	-72(%rbp), %rdx
	movl	$.LC18, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 790 5
	movq	-72(%rbp), %rax
	subq	-24(%rbp), %rax
	movq	%rax, %rdx
	movq	stderr(%rip), %rax
	movl	$.LC19, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 792 5
	movq	stderr(%rip), %rax
	movq	-120(%rbp), %rdx
	movl	$.LC20, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 794 13
	movq	-120(%rbp), %rax
	testq	%rax, %rax
	js	.L47
	pxor	%xmm0, %xmm0
	cvtsi2sdq	%rax, %xmm0
	jmp	.L48
.L47:
	movq	%rax, %rdx
	shrq	%rdx
	andl	$1, %eax
	orq	%rax, %rdx
	pxor	%xmm0, %xmm0
	cvtsi2sdq	%rdx, %xmm0
	addsd	%xmm0, %xmm0
.L48:
	.loc 1 794 36
	movq	-88(%rbp), %rax
	testq	%rax, %rax
	js	.L49
	pxor	%xmm1, %xmm1
	cvtsi2sdq	%rax, %xmm1
	jmp	.L50
.L49:
	movq	%rax, %rdx
	shrq	%rdx
	andl	$1, %eax
	orq	%rax, %rdx
	pxor	%xmm1, %xmm1
	cvtsi2sdq	%rdx, %xmm1
	addsd	%xmm1, %xmm1
.L50:
	.loc 1 793 5
	divsd	%xmm1, %xmm0
	movq	%xmm0, %rdx
	movq	stderr(%rip), %rax
	movq	%rdx, %xmm0
	movl	$.LC21, %esi
	movq	%rax, %rdi
	movl	$1, %eax
	call	fprintf
	.loc 1 795 5
	movq	stderr(%rip), %rax
	movl	-76(%rbp), %edx
	movl	$.LC22, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 796 5
	cmpl	$0, -80(%rbp)
	je	.L51
	.loc 1 796 5 is_stmt 0 discriminator 1
	movl	$.LC23, %edx
	jmp	.L52
.L51:
	.loc 1 796 5 discriminator 2
	movl	$.LC24, %edx
.L52:
	.loc 1 796 5 discriminator 4
	movq	stderr(%rip), %rax
	movl	$.LC25, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 798 5 is_stmt 1 discriminator 4
	cmpl	$0, -80(%rbp)
	je	.L53
	.loc 1 798 5 is_stmt 0 discriminator 1
	movl	$.LC26, %edx
	jmp	.L54
.L53:
	.loc 1 798 5 discriminator 2
	movl	$.LC27, %edx
.L54:
	.loc 1 798 5 discriminator 4
	movq	stderr(%rip), %rax
	movl	$.LC28, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 800 5 is_stmt 1 discriminator 4
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$52, %edx
	movl	$1, %esi
	movl	$.LC29, %edi
	call	fwrite
	.loc 1 801 5 discriminator 4
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$24, %edx
	movl	$1, %esi
	movl	$.LC30, %edi
	call	fwrite
	.loc 1 802 5 discriminator 4
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$76, %edx
	movl	$1, %esi
	movl	$.LC31, %edi
	call	fwrite
	.loc 1 804 5 discriminator 4
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$38, %edx
	movl	$1, %esi
	movl	$.LC32, %edi
	call	fwrite
	.loc 1 805 5 discriminator 4
	movq	stderr(%rip), %rax
	movq	%rax, %rcx
	movl	$49, %edx
	movl	$1, %esi
	movl	$.LC33, %edi
	call	fwrite
	.loc 1 806 5 discriminator 4
	movq	stderr(%rip), %rax
	movl	-12(%rbp), %edx
	movl	$.LC34, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 807 5 discriminator 4
	movq	stderr(%rip), %rax
	movq	-24(%rbp), %rdx
	movl	$.LC35, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 809 5 discriminator 4
	movq	g_sink(%rip), %rdx
	movq	stderr(%rip), %rax
	movl	$.LC36, %esi
	movq	%rax, %rdi
	movl	$0, %eax
	call	fprintf
	.loc 1 823 5 discriminator 4
	movl	$.LC37, %edi
	call	puts
.LBB30:
	.loc 1 824 19 discriminator 4
	movq	$0, -40(%rbp)
	.loc 1 824 5 discriminator 4
	jmp	.L55
.L58:
	.loc 1 825 20
	movq	-40(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-128(%rbp), %rax
	addq	%rdx, %rax
	movq	(%rax), %rax
	.loc 1 825 12
	cmpq	$-1, %rax
	je	.L60
	.loc 1 827 26
	movq	-40(%rbp), %rax
	leaq	0(,%rax,8), %rdx
	movq	-128(%rbp), %rax
	addq	%rdx, %rax
	.loc 1 826 9
	movq	(%rax), %rdx
	movq	-64(%rbp), %rcx
	movq	-40(%rbp), %rax
	movq	%rax, %rsi
	movl	$.LC38, %edi
	movl	$0, %eax
	call	printf
	jmp	.L57
.L60:
	.loc 1 825 44
	nop
.L57:
	.loc 1 824 44 discriminator 2
	addq	$1, -40(%rbp)
.L55:
	.loc 1 824 28 discriminator 1
	movq	-40(%rbp), %rax
	cmpq	-72(%rbp), %rax
	jb	.L58
.LBE30:
	.loc 1 830 5
	movq	-128(%rbp), %rax
	movq	%rax, %rdi
	call	free
	.loc 1 831 5
	movq	-96(%rbp), %rax
	movq	%rax, %rdi
	call	free
	.loc 1 832 12
	movl	$0, %eax
.L59:
	.loc 1 833 1 discriminator 1
	leave
	.cfi_def_cfa 7, 8
	ret
	.cfi_endproc
.LFE4379:
	.size	main, .-main
.Letext0:
	.file 4 "/usr/lib/gcc/x86_64-redhat-linux/11/include/stddef.h"
	.file 5 "/usr/include/bits/types.h"
	.file 6 "/usr/include/bits/types/struct_FILE.h"
	.file 7 "/usr/include/bits/types/FILE.h"
	.file 8 "/usr/include/bits/stdint-uintn.h"
	.file 9 "/usr/include/stdio.h"
	.file 10 "/usr/include/stdlib.h"
	.file 11 "/usr/include/string.h"
	.section	.debug_info,"",@progbits
.Ldebug_info0:
	.long	0x9bf
	.value	0x5
	.byte	0x1
	.byte	0x8
	.long	.Ldebug_abbrev0
	.uleb128 0x17
	.long	.LASF106
	.byte	0x1d
	.long	.LASF0
	.long	.LASF1
	.quad	.Ltext0
	.quad	.Letext0-.Ltext0
	.long	.Ldebug_line0
	.uleb128 0x8
	.long	.LASF8
	.byte	0x4
	.byte	0xd1
	.byte	0x17
	.long	0x3a
	.uleb128 0x6
	.byte	0x8
	.byte	0x7
	.long	.LASF2
	.uleb128 0x6
	.byte	0x4
	.byte	0x7
	.long	.LASF3
	.uleb128 0x18
	.byte	0x8
	.uleb128 0x6
	.byte	0x1
	.byte	0x8
	.long	.LASF4
	.uleb128 0x6
	.byte	0x2
	.byte	0x7
	.long	.LASF5
	.uleb128 0x6
	.byte	0x1
	.byte	0x6
	.long	.LASF6
	.uleb128 0x6
	.byte	0x2
	.byte	0x5
	.long	.LASF7
	.uleb128 0x19
	.byte	0x4
	.byte	0x5
	.string	"int"
	.uleb128 0x8
	.long	.LASF9
	.byte	0x5
	.byte	0x2a
	.byte	0x16
	.long	0x41
	.uleb128 0x6
	.byte	0x8
	.byte	0x5
	.long	.LASF10
	.uleb128 0x8
	.long	.LASF11
	.byte	0x5
	.byte	0x2d
	.byte	0x1b
	.long	0x3a
	.uleb128 0x8
	.long	.LASF12
	.byte	0x5
	.byte	0x98
	.byte	0x19
	.long	0x79
	.uleb128 0x8
	.long	.LASF13
	.byte	0x5
	.byte	0x99
	.byte	0x1b
	.long	0x79
	.uleb128 0x5
	.long	0xa9
	.uleb128 0x6
	.byte	0x1
	.byte	0x6
	.long	.LASF14
	.uleb128 0x1a
	.long	0xa9
	.uleb128 0x1b
	.long	.LASF107
	.byte	0xd8
	.byte	0x6
	.byte	0x33
	.byte	0x8
	.long	0x21f
	.uleb128 0x1
	.long	.LASF15
	.byte	0x35
	.byte	0x7
	.long	0x66
	.byte	0
	.uleb128 0x1
	.long	.LASF16
	.byte	0x38
	.byte	0x9
	.long	0xa4
	.byte	0x8
	.uleb128 0x1
	.long	.LASF17
	.byte	0x39
	.byte	0x9
	.long	0xa4
	.byte	0x10
	.uleb128 0x1
	.long	.LASF18
	.byte	0x3a
	.byte	0x9
	.long	0xa4
	.byte	0x18
	.uleb128 0x1
	.long	.LASF19
	.byte	0x3b
	.byte	0x9
	.long	0xa4
	.byte	0x20
	.uleb128 0x1
	.long	.LASF20
	.byte	0x3c
	.byte	0x9
	.long	0xa4
	.byte	0x28
	.uleb128 0x1
	.long	.LASF21
	.byte	0x3d
	.byte	0x9
	.long	0xa4
	.byte	0x30
	.uleb128 0x1
	.long	.LASF22
	.byte	0x3e
	.byte	0x9
	.long	0xa4
	.byte	0x38
	.uleb128 0x1
	.long	.LASF23
	.byte	0x3f
	.byte	0x9
	.long	0xa4
	.byte	0x40
	.uleb128 0x1
	.long	.LASF24
	.byte	0x42
	.byte	0x9
	.long	0xa4
	.byte	0x48
	.uleb128 0x1
	.long	.LASF25
	.byte	0x43
	.byte	0x9
	.long	0xa4
	.byte	0x50
	.uleb128 0x1
	.long	.LASF26
	.byte	0x44
	.byte	0x9
	.long	0xa4
	.byte	0x58
	.uleb128 0x1
	.long	.LASF27
	.byte	0x46
	.byte	0x16
	.long	0x238
	.byte	0x60
	.uleb128 0x1
	.long	.LASF28
	.byte	0x48
	.byte	0x14
	.long	0x23d
	.byte	0x68
	.uleb128 0x1
	.long	.LASF29
	.byte	0x4a
	.byte	0x7
	.long	0x66
	.byte	0x70
	.uleb128 0x1
	.long	.LASF30
	.byte	0x51
	.byte	0x7
	.long	0x66
	.byte	0x74
	.uleb128 0x1
	.long	.LASF31
	.byte	0x53
	.byte	0xb
	.long	0x8c
	.byte	0x78
	.uleb128 0x1
	.long	.LASF32
	.byte	0x56
	.byte	0x12
	.long	0x51
	.byte	0x80
	.uleb128 0x1
	.long	.LASF33
	.byte	0x57
	.byte	0xf
	.long	0x58
	.byte	0x82
	.uleb128 0x1
	.long	.LASF34
	.byte	0x58
	.byte	0x8
	.long	0x242
	.byte	0x83
	.uleb128 0x1
	.long	.LASF35
	.byte	0x5a
	.byte	0xf
	.long	0x252
	.byte	0x88
	.uleb128 0x1
	.long	.LASF36
	.byte	0x62
	.byte	0xd
	.long	0x98
	.byte	0x90
	.uleb128 0x1
	.long	.LASF37
	.byte	0x64
	.byte	0x17
	.long	0x25c
	.byte	0x98
	.uleb128 0x1
	.long	.LASF38
	.byte	0x65
	.byte	0x19
	.long	0x266
	.byte	0xa0
	.uleb128 0x1
	.long	.LASF39
	.byte	0x66
	.byte	0x14
	.long	0x23d
	.byte	0xa8
	.uleb128 0x1
	.long	.LASF40
	.byte	0x67
	.byte	0x9
	.long	0x48
	.byte	0xb0
	.uleb128 0x1
	.long	.LASF41
	.byte	0x68
	.byte	0xa
	.long	0x2e
	.byte	0xb8
	.uleb128 0x1
	.long	.LASF42
	.byte	0x69
	.byte	0x7
	.long	0x66
	.byte	0xc0
	.uleb128 0x1
	.long	.LASF43
	.byte	0x75
	.byte	0x8
	.long	0x26b
	.byte	0xc4
	.byte	0
	.uleb128 0x8
	.long	.LASF44
	.byte	0x7
	.byte	0x7
	.byte	0x19
	.long	0xb5
	.uleb128 0x1c
	.long	.LASF108
	.byte	0x6
	.byte	0x2d
	.byte	0xe
	.uleb128 0xd
	.long	.LASF45
	.uleb128 0x5
	.long	0x233
	.uleb128 0x5
	.long	0xb5
	.uleb128 0x11
	.long	0xa9
	.long	0x252
	.uleb128 0x12
	.long	0x3a
	.byte	0
	.byte	0
	.uleb128 0x5
	.long	0x22b
	.uleb128 0xd
	.long	.LASF46
	.uleb128 0x5
	.long	0x257
	.uleb128 0xd
	.long	.LASF47
	.uleb128 0x5
	.long	0x261
	.uleb128 0x11
	.long	0xa9
	.long	0x27b
	.uleb128 0x12
	.long	0x3a
	.byte	0x13
	.byte	0
	.uleb128 0x5
	.long	0x21f
	.uleb128 0xe
	.long	0x27b
	.uleb128 0x1d
	.long	.LASF109
	.byte	0x9
	.byte	0x8b
	.byte	0xe
	.long	0x27b
	.uleb128 0x6
	.byte	0x8
	.byte	0x5
	.long	.LASF48
	.uleb128 0x8
	.long	.LASF49
	.byte	0x8
	.byte	0x1a
	.byte	0x14
	.long	0x6d
	.uleb128 0x8
	.long	.LASF50
	.byte	0x8
	.byte	0x1b
	.byte	0x14
	.long	0x80
	.uleb128 0x6
	.byte	0x10
	.byte	0x4
	.long	.LASF51
	.uleb128 0x6
	.byte	0x8
	.byte	0x7
	.long	.LASF52
	.uleb128 0x6
	.byte	0x4
	.byte	0x4
	.long	.LASF53
	.uleb128 0x6
	.byte	0x8
	.byte	0x4
	.long	.LASF54
	.uleb128 0x8
	.long	.LASF55
	.byte	0x1
	.byte	0xe7
	.byte	0x11
	.long	0x2d8
	.uleb128 0x5
	.long	0x48
	.uleb128 0x2
	.long	.LASF56
	.value	0x168
	.byte	0x11
	.long	0x298
	.uleb128 0x9
	.byte	0x3
	.quad	g_rng_state
	.uleb128 0x2
	.long	.LASF57
	.value	0x248
	.byte	0x17
	.long	0x309
	.uleb128 0x9
	.byte	0x3
	.quad	g_sink
	.uleb128 0x5
	.long	0x30e
	.uleb128 0x1e
	.uleb128 0xa
	.long	.LASF58
	.byte	0x9
	.value	0x15e
	.byte	0xc
	.long	0x66
	.long	0x327
	.uleb128 0x3
	.long	0x327
	.uleb128 0x13
	.byte	0
	.uleb128 0x5
	.long	0xb0
	.uleb128 0xe
	.long	0x327
	.uleb128 0xb
	.long	.LASF59
	.byte	0xa
	.byte	0x68
	.byte	0xc
	.long	0x66
	.long	0x347
	.uleb128 0x3
	.long	0x327
	.byte	0
	.uleb128 0xb
	.long	.LASF60
	.byte	0xa
	.byte	0xb4
	.byte	0x1a
	.long	0x3a
	.long	0x367
	.uleb128 0x3
	.long	0x32c
	.uleb128 0x3
	.long	0x36c
	.uleb128 0x3
	.long	0x66
	.byte	0
	.uleb128 0x5
	.long	0xa4
	.uleb128 0xe
	.long	0x367
	.uleb128 0xb
	.long	.LASF61
	.byte	0xa
	.byte	0xcd
	.byte	0x1f
	.long	0x2b7
	.long	0x391
	.uleb128 0x3
	.long	0x32c
	.uleb128 0x3
	.long	0x36c
	.uleb128 0x3
	.long	0x66
	.byte	0
	.uleb128 0x1f
	.long	.LASF110
	.byte	0xa
	.value	0x22a
	.byte	0xd
	.long	0x3a4
	.uleb128 0x3
	.long	0x48
	.byte	0
	.uleb128 0xa
	.long	.LASF62
	.byte	0xa
	.value	0x21b
	.byte	0xe
	.long	0x48
	.long	0x3bb
	.uleb128 0x3
	.long	0x2e
	.byte	0
	.uleb128 0xb
	.long	.LASF63
	.byte	0xb
	.byte	0x3d
	.byte	0xe
	.long	0x48
	.long	0x3db
	.uleb128 0x3
	.long	0x48
	.uleb128 0x3
	.long	0x66
	.uleb128 0x3
	.long	0x2e
	.byte	0
	.uleb128 0x20
	.long	.LASF64
	.byte	0xa
	.value	0x26e
	.byte	0xd
	.long	0x3ee
	.uleb128 0x3
	.long	0x66
	.byte	0
	.uleb128 0xa
	.long	.LASF65
	.byte	0x9
	.value	0x158
	.byte	0xc
	.long	0x66
	.long	0x40b
	.uleb128 0x3
	.long	0x280
	.uleb128 0x3
	.long	0x32c
	.uleb128 0x13
	.byte	0
	.uleb128 0xa
	.long	.LASF66
	.byte	0xa
	.value	0x24f
	.byte	0xe
	.long	0x48
	.long	0x427
	.uleb128 0x3
	.long	0x2e
	.uleb128 0x3
	.long	0x2e
	.byte	0
	.uleb128 0x21
	.long	.LASF111
	.byte	0x1
	.value	0x24f
	.byte	0x5
	.long	0x66
	.quad	.LFB4379
	.quad	.LFE4379-.LFB4379
	.uleb128 0x1
	.byte	0x9c
	.long	0x607
	.uleb128 0x7
	.long	.LASF67
	.value	0x24f
	.byte	0xe
	.long	0x66
	.uleb128 0x3
	.byte	0x91
	.sleb128 -196
	.uleb128 0x7
	.long	.LASF68
	.value	0x24f
	.byte	0x1b
	.long	0x367
	.uleb128 0x3
	.byte	0x91
	.sleb128 -208
	.uleb128 0x2
	.long	.LASF69
	.value	0x25b
	.byte	0xe
	.long	0x2e
	.uleb128 0x2
	.byte	0x91
	.sleb128 -64
	.uleb128 0x2
	.long	.LASF70
	.value	0x25c
	.byte	0xe
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -72
	.uleb128 0x2
	.long	.LASF71
	.value	0x25d
	.byte	0xe
	.long	0x2a4
	.uleb128 0x3
	.byte	0x91
	.sleb128 -80
	.uleb128 0x2
	.long	.LASF72
	.value	0x25e
	.byte	0xe
	.long	0x2a4
	.uleb128 0x3
	.byte	0x91
	.sleb128 -88
	.uleb128 0x2
	.long	.LASF73
	.value	0x25f
	.byte	0xe
	.long	0x298
	.uleb128 0x3
	.byte	0x91
	.sleb128 -92
	.uleb128 0x2
	.long	.LASF74
	.value	0x260
	.byte	0xe
	.long	0x66
	.uleb128 0x3
	.byte	0x91
	.sleb128 -96
	.uleb128 0x2
	.long	.LASF75
	.value	0x290
	.byte	0xc
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -104
	.uleb128 0x2
	.long	.LASF76
	.value	0x29a
	.byte	0xf
	.long	0x2cc
	.uleb128 0x3
	.byte	0x91
	.sleb128 -168
	.uleb128 0x2
	.long	.LASF77
	.value	0x29b
	.byte	0xf
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -176
	.uleb128 0x2
	.long	.LASF78
	.value	0x29c
	.byte	0xf
	.long	0x48
	.uleb128 0x3
	.byte	0x91
	.sleb128 -112
	.uleb128 0x4
	.string	"p"
	.value	0x29e
	.byte	0xf
	.long	0x2cc
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.uleb128 0x2
	.long	.LASF79
	.value	0x2b6
	.byte	0xe
	.long	0x2a4
	.uleb128 0x3
	.byte	0x91
	.sleb128 -120
	.uleb128 0x2
	.long	.LASF80
	.value	0x2b7
	.byte	0xe
	.long	0x2a4
	.uleb128 0x3
	.byte	0x91
	.sleb128 -128
	.uleb128 0x2
	.long	.LASF81
	.value	0x2b8
	.byte	0xe
	.long	0x2a4
	.uleb128 0x3
	.byte	0x91
	.sleb128 -136
	.uleb128 0x2
	.long	.LASF82
	.value	0x2c9
	.byte	0xf
	.long	0x607
	.uleb128 0x3
	.byte	0x91
	.sleb128 -144
	.uleb128 0x2
	.long	.LASF83
	.value	0x2ea
	.byte	0xe
	.long	0x41
	.uleb128 0x2
	.byte	0x91
	.sleb128 -28
	.uleb128 0x2
	.long	.LASF84
	.value	0x2eb
	.byte	0xe
	.long	0x2a4
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0xf
	.quad	.LBB28
	.quad	.LBE28-.LBB28
	.long	0x5e7
	.uleb128 0x4
	.string	"r"
	.value	0x2ed
	.byte	0x13
	.long	0x2a4
	.uleb128 0x2
	.byte	0x91
	.sleb128 -48
	.uleb128 0x9
	.quad	.LBB29
	.quad	.LBE29-.LBB29
	.uleb128 0x2
	.long	.LASF85
	.value	0x2ee
	.byte	0x12
	.long	0x41
	.uleb128 0x3
	.byte	0x91
	.sleb128 -180
	.uleb128 0x2
	.long	.LASF86
	.value	0x2ee
	.byte	0x19
	.long	0x41
	.uleb128 0x3
	.byte	0x91
	.sleb128 -184
	.uleb128 0x4
	.string	"t0"
	.value	0x2f0
	.byte	0x12
	.long	0x2a4
	.uleb128 0x3
	.byte	0x91
	.sleb128 -152
	.uleb128 0x4
	.string	"t1"
	.value	0x2f2
	.byte	0x12
	.long	0x2a4
	.uleb128 0x3
	.byte	0x91
	.sleb128 -160
	.byte	0
	.byte	0
	.uleb128 0x9
	.quad	.LBB30
	.quad	.LBE30-.LBB30
	.uleb128 0x4
	.string	"r"
	.value	0x338
	.byte	0x13
	.long	0x2a4
	.uleb128 0x2
	.byte	0x91
	.sleb128 -56
	.byte	0
	.byte	0
	.uleb128 0x5
	.long	0x2a4
	.uleb128 0xc
	.long	.LASF88
	.value	0x23c
	.byte	0x12
	.long	0x2cc
	.quad	.LFB4378
	.quad	.LFE4378-.LFB4378
	.uleb128 0x1
	.byte	0x9c
	.long	0x66b
	.uleb128 0x22
	.string	"p"
	.byte	0x1
	.value	0x23c
	.byte	0x22
	.long	0x2cc
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0x7
	.long	.LASF87
	.value	0x23c
	.byte	0x2e
	.long	0x2a4
	.uleb128 0x2
	.byte	0x91
	.sleb128 -48
	.uleb128 0x9
	.quad	.LBB27
	.quad	.LBE27-.LBB27
	.uleb128 0x4
	.string	"i"
	.value	0x23e
	.byte	0x13
	.long	0x2a4
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.byte	0
	.byte	0
	.uleb128 0x14
	.long	.LASF89
	.value	0x19f
	.byte	0xe
	.long	0x48
	.quad	.LFB4377
	.quad	.LFE4377-.LFB4377
	.uleb128 0x1
	.byte	0x9c
	.long	0x7f2
	.uleb128 0x7
	.long	.LASF75
	.value	0x19f
	.byte	0x20
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -120
	.uleb128 0x7
	.long	.LASF70
	.value	0x19f
	.byte	0x32
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -128
	.uleb128 0x7
	.long	.LASF74
	.value	0x19f
	.byte	0x3f
	.long	0x66
	.uleb128 0x3
	.byte	0x91
	.sleb128 -132
	.uleb128 0x7
	.long	.LASF90
	.value	0x1a0
	.byte	0x24
	.long	0x7f2
	.uleb128 0x3
	.byte	0x91
	.sleb128 -144
	.uleb128 0x7
	.long	.LASF91
	.value	0x1a0
	.byte	0x37
	.long	0x7f7
	.uleb128 0x3
	.byte	0x91
	.sleb128 -152
	.uleb128 0x2
	.long	.LASF92
	.value	0x1a2
	.byte	0xc
	.long	0x2e
	.uleb128 0x2
	.byte	0x91
	.sleb128 -48
	.uleb128 0x2
	.long	.LASF93
	.value	0x1b3
	.byte	0xc
	.long	0x2e
	.uleb128 0x2
	.byte	0x91
	.sleb128 -56
	.uleb128 0x4
	.string	"buf"
	.value	0x1b6
	.byte	0x14
	.long	0x7fc
	.uleb128 0x2
	.byte	0x91
	.sleb128 -64
	.uleb128 0x2
	.long	.LASF94
	.value	0x1d2
	.byte	0xd
	.long	0x7f7
	.uleb128 0x3
	.byte	0x91
	.sleb128 -72
	.uleb128 0xf
	.quad	.LBB22
	.quad	.LBE22-.LBB22
	.long	0x73d
	.uleb128 0x4
	.string	"i"
	.value	0x1d8
	.byte	0x11
	.long	0x2e
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.byte	0
	.uleb128 0xf
	.quad	.LBB23
	.quad	.LBE23-.LBB23
	.long	0x790
	.uleb128 0x4
	.string	"i"
	.value	0x1ec
	.byte	0x15
	.long	0x2e
	.uleb128 0x2
	.byte	0x91
	.sleb128 -32
	.uleb128 0x9
	.quad	.LBB24
	.quad	.LBE24-.LBB24
	.uleb128 0x4
	.string	"j"
	.value	0x1ed
	.byte	0x16
	.long	0x298
	.uleb128 0x3
	.byte	0x91
	.sleb128 -76
	.uleb128 0x4
	.string	"tmp"
	.value	0x1ee
	.byte	0x16
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -88
	.byte	0
	.byte	0
	.uleb128 0x9
	.quad	.LBB25
	.quad	.LBE25-.LBB25
	.uleb128 0x4
	.string	"i"
	.value	0x1ff
	.byte	0x11
	.long	0x2e
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0x9
	.quad	.LBB26
	.quad	.LBE26-.LBB26
	.uleb128 0x4
	.string	"cur"
	.value	0x200
	.byte	0x10
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -96
	.uleb128 0x2
	.long	.LASF95
	.value	0x201
	.byte	0x10
	.long	0x2e
	.uleb128 0x3
	.byte	0x91
	.sleb128 -104
	.uleb128 0x2
	.long	.LASF96
	.value	0x203
	.byte	0x10
	.long	0x2d8
	.uleb128 0x3
	.byte	0x91
	.sleb128 -112
	.byte	0
	.byte	0
	.byte	0
	.uleb128 0x5
	.long	0x2cc
	.uleb128 0x5
	.long	0x2e
	.uleb128 0x5
	.long	0x4a
	.uleb128 0x14
	.long	.LASF97
	.value	0x17b
	.byte	0x11
	.long	0x298
	.quad	.LFB4376
	.quad	.LFE4376-.LFB4376
	.uleb128 0x1
	.byte	0x9c
	.long	0x85e
	.uleb128 0x7
	.long	.LASF98
	.value	0x17b
	.byte	0x2d
	.long	0x298
	.uleb128 0x2
	.byte	0x91
	.sleb128 -36
	.uleb128 0x2
	.long	.LASF99
	.value	0x17d
	.byte	0xe
	.long	0x298
	.uleb128 0x2
	.byte	0x91
	.sleb128 -20
	.uleb128 0x2
	.long	.LASF100
	.value	0x180
	.byte	0xe
	.long	0x298
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.uleb128 0x4
	.string	"r"
	.value	0x181
	.byte	0xe
	.long	0x298
	.uleb128 0x2
	.byte	0x91
	.sleb128 -28
	.byte	0
	.uleb128 0xc
	.long	.LASF101
	.value	0x16a
	.byte	0x11
	.long	0x298
	.quad	.LFB4375
	.quad	.LFE4375-.LFB4375
	.uleb128 0x1
	.byte	0x9c
	.long	0x88e
	.uleb128 0x4
	.string	"x"
	.value	0x16c
	.byte	0xe
	.long	0x298
	.uleb128 0x2
	.byte	0x91
	.sleb128 -20
	.byte	0
	.uleb128 0xc
	.long	.LASF102
	.value	0x13e
	.byte	0x18
	.long	0x2a4
	.quad	.LFB4374
	.quad	.LFE4374-.LFB4374
	.uleb128 0x1
	.byte	0x9c
	.long	0x908
	.uleb128 0x7
	.long	.LASF103
	.value	0x13e
	.byte	0x2b
	.long	0x908
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0x4
	.string	"t"
	.value	0x140
	.byte	0xe
	.long	0x2a4
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.uleb128 0x15
	.long	0x9a8
	.quad	.LBB18
	.quad	.LBE18-.LBB18
	.value	0x144
	.long	0x8f0
	.uleb128 0x16
	.long	0x9b5
	.uleb128 0x2
	.byte	0x91
	.sleb128 -32
	.byte	0
	.uleb128 0x10
	.long	0x99e
	.quad	.LBB20
	.quad	.LBE20-.LBB20
	.value	0x148
	.byte	0
	.uleb128 0x5
	.long	0x41
	.uleb128 0xc
	.long	.LASF104
	.value	0x124
	.byte	0x18
	.long	0x2a4
	.quad	.LFB4373
	.quad	.LFE4373-.LFB4373
	.uleb128 0x1
	.byte	0x9c
	.long	0x99e
	.uleb128 0x7
	.long	.LASF103
	.value	0x124
	.byte	0x2c
	.long	0x908
	.uleb128 0x2
	.byte	0x91
	.sleb128 -40
	.uleb128 0x4
	.string	"t"
	.value	0x126
	.byte	0xe
	.long	0x2a4
	.uleb128 0x2
	.byte	0x91
	.sleb128 -24
	.uleb128 0x10
	.long	0x99e
	.quad	.LBB12
	.quad	.LBE12-.LBB12
	.value	0x131
	.uleb128 0x15
	.long	0x9a8
	.quad	.LBB14
	.quad	.LBE14-.LBB14
	.value	0x133
	.long	0x986
	.uleb128 0x16
	.long	0x9b5
	.uleb128 0x2
	.byte	0x91
	.sleb128 -32
	.byte	0
	.uleb128 0x10
	.long	0x99e
	.quad	.LBB16
	.quad	.LBE16-.LBB16
	.value	0x139
	.byte	0
	.uleb128 0x23
	.long	.LASF112
	.byte	0x2
	.value	0x5f6
	.byte	0x1
	.byte	0x3
	.uleb128 0x24
	.long	.LASF105
	.byte	0x3
	.byte	0x7a
	.byte	0x1
	.long	0x2b7
	.byte	0x3
	.uleb128 0x25
	.string	"__A"
	.byte	0x3
	.byte	0x7a
	.byte	0x19
	.long	0x908
	.byte	0
	.byte	0
	.section	.debug_abbrev,"",@progbits
.Ldebug_abbrev0:
	.uleb128 0x1
	.uleb128 0xd
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 6
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x38
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x2
	.uleb128 0x34
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x3
	.uleb128 0x5
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x4
	.uleb128 0x34
	.byte	0
	.uleb128 0x3
	.uleb128 0x8
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x5
	.uleb128 0xf
	.byte	0
	.uleb128 0xb
	.uleb128 0x21
	.sleb128 8
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x6
	.uleb128 0x24
	.byte	0
	.uleb128 0xb
	.uleb128 0xb
	.uleb128 0x3e
	.uleb128 0xb
	.uleb128 0x3
	.uleb128 0xe
	.byte	0
	.byte	0
	.uleb128 0x7
	.uleb128 0x5
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x8
	.uleb128 0x16
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x9
	.uleb128 0xb
	.byte	0x1
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.byte	0
	.byte	0
	.uleb128 0xa
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x3c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0xb
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x3c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0xc
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x40
	.uleb128 0x18
	.uleb128 0x7a
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0xd
	.uleb128 0x13
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3c
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0xe
	.uleb128 0x37
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0xf
	.uleb128 0xb
	.byte	0x1
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x10
	.uleb128 0x1d
	.byte	0
	.uleb128 0x31
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x58
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x59
	.uleb128 0x5
	.uleb128 0x57
	.uleb128 0x21
	.sleb128 5
	.byte	0
	.byte	0
	.uleb128 0x11
	.uleb128 0x1
	.byte	0x1
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x12
	.uleb128 0x21
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2f
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x13
	.uleb128 0x18
	.byte	0
	.byte	0
	.byte	0
	.uleb128 0x14
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x40
	.uleb128 0x18
	.uleb128 0x7c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x15
	.uleb128 0x1d
	.byte	0x1
	.uleb128 0x31
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x58
	.uleb128 0x21
	.sleb128 1
	.uleb128 0x59
	.uleb128 0x5
	.uleb128 0x57
	.uleb128 0x21
	.sleb128 9
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x16
	.uleb128 0x5
	.byte	0
	.uleb128 0x31
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x17
	.uleb128 0x11
	.byte	0x1
	.uleb128 0x25
	.uleb128 0xe
	.uleb128 0x13
	.uleb128 0xb
	.uleb128 0x3
	.uleb128 0x1f
	.uleb128 0x1b
	.uleb128 0x1f
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x10
	.uleb128 0x17
	.byte	0
	.byte	0
	.uleb128 0x18
	.uleb128 0xf
	.byte	0
	.uleb128 0xb
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x19
	.uleb128 0x24
	.byte	0
	.uleb128 0xb
	.uleb128 0xb
	.uleb128 0x3e
	.uleb128 0xb
	.uleb128 0x3
	.uleb128 0x8
	.byte	0
	.byte	0
	.uleb128 0x1a
	.uleb128 0x26
	.byte	0
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x1b
	.uleb128 0x13
	.byte	0x1
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0xb
	.uleb128 0xb
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x1c
	.uleb128 0x16
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.byte	0
	.byte	0
	.uleb128 0x1d
	.uleb128 0x34
	.byte	0
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3c
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0x1e
	.uleb128 0x35
	.byte	0
	.byte	0
	.byte	0
	.uleb128 0x1f
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x3c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x20
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x87
	.uleb128 0x19
	.uleb128 0x3c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x21
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x11
	.uleb128 0x1
	.uleb128 0x12
	.uleb128 0x7
	.uleb128 0x40
	.uleb128 0x18
	.uleb128 0x7c
	.uleb128 0x19
	.uleb128 0x1
	.uleb128 0x13
	.byte	0
	.byte	0
	.uleb128 0x22
	.uleb128 0x5
	.byte	0
	.uleb128 0x3
	.uleb128 0x8
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x2
	.uleb128 0x18
	.byte	0
	.byte	0
	.uleb128 0x23
	.uleb128 0x2e
	.byte	0
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0x5
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x20
	.uleb128 0xb
	.uleb128 0x34
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0x24
	.uleb128 0x2e
	.byte	0x1
	.uleb128 0x3f
	.uleb128 0x19
	.uleb128 0x3
	.uleb128 0xe
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x27
	.uleb128 0x19
	.uleb128 0x49
	.uleb128 0x13
	.uleb128 0x20
	.uleb128 0xb
	.uleb128 0x34
	.uleb128 0x19
	.byte	0
	.byte	0
	.uleb128 0x25
	.uleb128 0x5
	.byte	0
	.uleb128 0x3
	.uleb128 0x8
	.uleb128 0x3a
	.uleb128 0xb
	.uleb128 0x3b
	.uleb128 0xb
	.uleb128 0x39
	.uleb128 0xb
	.uleb128 0x49
	.uleb128 0x13
	.byte	0
	.byte	0
	.byte	0
	.section	.debug_aranges,"",@progbits
	.long	0x2c
	.value	0x2
	.long	.Ldebug_info0
	.byte	0x8
	.byte	0
	.value	0
	.value	0
	.quad	.Ltext0
	.quad	.Letext0-.Ltext0
	.quad	0
	.quad	0
	.section	.debug_line,"",@progbits
.Ldebug_line0:
	.section	.debug_str,"MS",@progbits,1
.LASF31:
	.string	"_old_offset"
.LASF102:
	.string	"tsc_stop"
.LASF54:
	.string	"double"
.LASF107:
	.string	"_IO_FILE"
.LASF26:
	.string	"_IO_save_end"
.LASF7:
	.string	"short int"
.LASF8:
	.string	"size_t"
.LASF62:
	.string	"malloc"
.LASF97:
	.string	"rng_below_or_equal"
.LASF90:
	.string	"entry_out"
.LASF36:
	.string	"_offset"
.LASF91:
	.string	"alloc_bytes_out"
.LASF111:
	.string	"main"
.LASF20:
	.string	"_IO_write_ptr"
.LASF15:
	.string	"_flags"
.LASF9:
	.string	"__uint32_t"
.LASF69:
	.string	"working_set_bytes"
.LASF35:
	.string	"_lock"
.LASF27:
	.string	"_markers"
.LASF17:
	.string	"_IO_read_end"
.LASF40:
	.string	"_freeres_buf"
.LASF85:
	.string	"aux_a"
.LASF86:
	.string	"aux_b"
.LASF110:
	.string	"free"
.LASF74:
	.string	"sequential"
.LASF32:
	.string	"_cur_column"
.LASF53:
	.string	"float"
.LASF44:
	.string	"FILE"
.LASF109:
	.string	"stderr"
.LASF48:
	.string	"long long int"
.LASF100:
	.string	"limit"
.LASF94:
	.string	"order"
.LASF63:
	.string	"memset"
.LASF57:
	.string	"g_sink"
.LASF58:
	.string	"printf"
.LASF103:
	.string	"aux_out"
.LASF98:
	.string	"bound"
.LASF82:
	.string	"samples"
.LASF104:
	.string	"tsc_start"
.LASF84:
	.string	"migrated_samples"
.LASF59:
	.string	"atoi"
.LASF79:
	.string	"warmup_by_lap"
.LASF68:
	.string	"argv"
.LASF4:
	.string	"unsigned char"
.LASF64:
	.string	"exit"
.LASF77:
	.string	"alloc_bytes"
.LASF51:
	.string	"long double"
.LASF60:
	.string	"strtoul"
.LASF99:
	.string	"modulus"
.LASF76:
	.string	"entry"
.LASF55:
	.string	"chain_ptr"
.LASF106:
	.string	"GNU C11 11.5.0 20240719 (Red Hat 11.5.0-14) -mtune=generic -march=x86-64-v2 -g -O0 -std=c11 -fno-omit-frame-pointer"
.LASF56:
	.string	"g_rng_state"
.LASF67:
	.string	"argc"
.LASF61:
	.string	"strtoull"
.LASF6:
	.string	"signed char"
.LASF50:
	.string	"uint64_t"
.LASF52:
	.string	"long long unsigned int"
.LASF49:
	.string	"uint32_t"
.LASF3:
	.string	"unsigned int"
.LASF45:
	.string	"_IO_marker"
.LASF34:
	.string	"_shortbuf"
.LASF81:
	.string	"warmup_steps"
.LASF96:
	.string	"slot"
.LASF19:
	.string	"_IO_write_base"
.LASF88:
	.string	"chase"
.LASF16:
	.string	"_IO_read_ptr"
.LASF87:
	.string	"steps"
.LASF23:
	.string	"_IO_buf_end"
.LASF112:
	.string	"_mm_lfence"
.LASF71:
	.string	"N_per_batch"
.LASF14:
	.string	"char"
.LASF10:
	.string	"long int"
.LASF73:
	.string	"seed"
.LASF38:
	.string	"_wide_data"
.LASF39:
	.string	"_freeres_list"
.LASF43:
	.string	"_unused2"
.LASF41:
	.string	"__pad5"
.LASF11:
	.string	"__uint64_t"
.LASF83:
	.string	"aux_first"
.LASF78:
	.string	"buffer"
.LASF5:
	.string	"short unsigned int"
.LASF66:
	.string	"aligned_alloc"
.LASF2:
	.string	"long unsigned int"
.LASF92:
	.string	"bytes"
.LASF21:
	.string	"_IO_write_end"
.LASF89:
	.string	"build_ring"
.LASF13:
	.string	"__off64_t"
.LASF105:
	.string	"__rdtscp"
.LASF29:
	.string	"_fileno"
.LASF28:
	.string	"_chain"
.LASF47:
	.string	"_IO_wide_data"
.LASF42:
	.string	"_mode"
.LASF12:
	.string	"__off_t"
.LASF25:
	.string	"_IO_backup_base"
.LASF80:
	.string	"warmup_by_batch"
.LASF22:
	.string	"_IO_buf_base"
.LASF30:
	.string	"_flags2"
.LASF46:
	.string	"_IO_codecvt"
.LASF18:
	.string	"_IO_read_base"
.LASF33:
	.string	"_vtable_offset"
.LASF37:
	.string	"_codecvt"
.LASF24:
	.string	"_IO_save_base"
.LASF101:
	.string	"xorshift32"
.LASF93:
	.string	"rounded"
.LASF70:
	.string	"spacing"
.LASF75:
	.string	"num_nodes"
.LASF65:
	.string	"fprintf"
.LASF72:
	.string	"num_samples"
.LASF95:
	.string	"next"
.LASF108:
	.string	"_IO_lock_t"
	.section	.debug_line_str,"MS",@progbits,1
.LASF1:
	.string	"/home/rrsood/ECE592_HW1"
.LASF0:
	.string	"/home/rrsood/ECE592_HW1/main_code/x86_64/cache_bench.c"
	.ident	"GCC: (GNU) 11.5.0 20240719 (Red Hat 11.5.0-14)"
	.section	.note.GNU-stack,"",@progbits
